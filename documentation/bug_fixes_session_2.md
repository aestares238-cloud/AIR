# Bug Fixes — Database, Contacts, and Pipeline

This document covers the bugs found and fixed during the same session as the hybrid anomaly detection implementation.

---

## Bug 1 — Missing Auto-Increment on All Table IDs

### Problem
Three tables were created without `SERIAL` / `BIGSERIAL` on their `id` column. PostgreSQL had no sequence to auto-generate IDs, so every `INSERT` without an explicit `id` failed with:

```
psycopg2.errors.NotNullViolation: null value in column "id" violates not-null constraint
```

This caused:
- `POST /telemetry` → 500 Internal Server Error
- `POST /contacts` → 500 Internal Server Error
- `POST /alerts` (internal) → 500 Internal Server Error

### Affected Tables

| Table | Fixed By |
|---|---|
| `telemetry` | `fix_telemetry_id.py` |
| `alerts` | `fix_alerts_id.py` |
| `contacts` | `fix_contacts_id.py` |

### Fix (run once per table)
```python
cur.execute("CREATE SEQUENCE IF NOT EXISTS <table>_id_seq")
cur.execute("SELECT setval('<table>_id_seq', COALESCE((SELECT MAX(id) FROM <table>), 0) + 1, false)")
cur.execute("ALTER TABLE <table> ALTER COLUMN id SET DEFAULT nextval('<table>_id_seq')")
conn.commit()
```

> These scripts are safe to run multiple times (`IF NOT EXISTS`). They do not affect existing data.

---

## Bug 2 — `contacts.enable` Type Mismatch (bool vs integer)

### Problem
The `contacts.enable` column is `INTEGER` in PostgreSQL (stores `1` or `0`), but the FastAPI endpoint was passing Python's native `True` / `False` boolean directly via psycopg2. PostgreSQL refuses to auto-cast boolean to integer:

```
psycopg2.errors.DatatypeMismatch: column "enable" is of type integer
but expression is of type boolean
```

### Fix — `services/contacts_api.py`
Cast to `int()` before passing to SQL in all three write operations:

```python
# create_contact
(payload.name, payload.ph_number, int(payload.enable))

# update_contact
(payload.name, payload.ph_number, int(payload.enable), contact_id)

# patch_enable
cur.execute("UPDATE contacts SET enable = %s WHERE id = %s", (int(enable), contact_id))
```

---

## Bug 3 — Phone Number Validation Mismatch

### Problem
The frontend HTML allowed 10–15 digits (`pattern="\d{10,15}"`) but the backend Pydantic model required exactly 11 (`^\d{11}$`). Any number with a different length caused a silent `422 Validation Error`.

### Fix — `services/contacts_api.py`
```python
# Before
ph_number: str = Field(..., pattern=r"^\d{11}$")

# After
ph_number: str = Field(..., pattern=r"^\d{10,15}$")
```

---

## Bug 4 — Contacts Form Never Checked API Response

### Problem
The Add Contact form submitted the POST request but never checked `res.ok`. The toast always showed "New contact added" regardless of whether the server returned `201` or `422` or `500`. Same issue applied to the Save button on existing contacts.

### Fix — `templates/pages/contacts.html`
```js
const res = await fetch('/contacts', { method: 'POST', ... });

if (res.ok) {
    // clear form, show success toast, reload list
} else {
    // parse error.detail from response, show error toast in red
}
```

---

## Bug 5 — `/telemetry` POST Blocking the Raspberry Pi

### Problem
`process_anomaly()` was called synchronously inside `POST /telemetry`. This meant:
- The Raspberry Pi had to wait for the full AI API call + SMS to complete before getting a response
- If the AI timed out (10–30 seconds), the HTTP request timed out first → 500 error to the Pi
- If `send_sms()` raised an exception, it propagated back up → 500 error

### Fix — `main.py`
Moved `process_anomaly()` to a `BackgroundTasks` function so the Pi always gets an instant `201` response:

```python
from fastapi import BackgroundTasks

@app.post("/telemetry", status_code=201)
def receive_telemetry(payload: Telemetry, background_tasks: BackgroundTasks):
    # ... store to DB ...
    if is_anom:
        def _safe_process(data):
            try:
                process_anomaly(data)
            except Exception as e:
                print(f"[ERROR] process_anomaly failed: {e}")
        background_tasks.add_task(_safe_process, payload_dict)

    return {"id": row_id, "status": "stored"}  # Pi gets this immediately
```

### Fix — `services/anomaly_reciever.py`
Wrapped `send_sms()` in `try/except` so an SMS failure never aborts the pipeline. The alert is always saved to the database before SMS is attempted:

```python
try:
    send_sms(sms_message)
except Exception as sms_err:
    print(f"SMS SEND FAILED (alert still saved): {sms_err}")
```

---

## SMS Gateway Note

The Traccar SMS gateway **requires an Android device** running the Traccar Client app with SMS permissions. **iOS is not supported** — Apple's sandboxing prevents third-party apps from sending SMS programmatically.

If an Android gateway device is unavailable, consider switching to a cloud SMS API such as **Semaphore** (Philippine numbers, free tier available at `semaphore.co`).
