from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from database import get_db_connection

LOCAL_TZ = timezone(timedelta(hours=8))

router = APIRouter()

class AlertIn(BaseModel):
    summary: str = Field(..., min_length=1)
    diagnoses: Optional[str] = None

class AlertOut(BaseModel):
    id: int
    timestamp: str
    summary: str
    diagnoses: Optional[str]

@router.get("/alerts", response_model=List[AlertOut])
def list_alerts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, timestamp::text, summary, diagnoses FROM alerts ORDER BY timestamp DESC, id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [AlertOut(**dict(r)) for r in rows]

@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, timestamp::text, summary, diagnoses FROM alerts WHERE id = %s",
        (alert_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertOut(**dict(row))

@router.post("/alerts", status_code=201, response_model=AlertOut)
def create_alert(payload: AlertIn):
    conn = get_db_connection()
    cur = conn.cursor()
    diagnoses_val = payload.diagnoses
    cur.execute(
        "INSERT INTO alerts (timestamp, summary, diagnoses) VALUES (%s, %s, %s) RETURNING id, timestamp::text",
        (
            datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            payload.summary,
            diagnoses_val,
        ),
    )
    inserted = cur.fetchone()
    alert_id = inserted["id"]
    timestamp = inserted["timestamp"]
    conn.commit()
    conn.close()
    return AlertOut(id=alert_id, timestamp=timestamp, summary=payload.summary, diagnoses=payload.diagnoses)

@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM alerts WHERE id = %s", (alert_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Alert not found")
    cur.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
    conn.commit()
    conn.close()
    return {}

@router.get("/alerts/by_issue", response_model=List[AlertOut])
def get_alerts_by_issue(issue: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, timestamp::text, summary, diagnoses FROM alerts WHERE summary = %s ORDER BY timestamp DESC, id DESC",
        (issue,),
    )
    rows = cur.fetchall()
    conn.close()
    return [AlertOut(**dict(r)) for r in rows]

@router.delete("/alerts/by_issue", response_model=dict)
def delete_alerts_by_issue(issue: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM alerts WHERE summary = %s", (issue,))
    row = cur.fetchone()
    count = row["cnt"] if row else 0
    cur.execute("DELETE FROM alerts WHERE summary = %s", (issue,))
    conn.commit()
    conn.close()
    return {"deleted": count}

@router.get("/alerts/table/drop", response_model=dict)
def drop_alerts_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS alerts")
    conn.commit()
    conn.close()
    return {"dropped": True}

@router.get("/alerts/table/reset", response_model=dict)
def reset_alerts_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE alerts RESTART IDENTITY")
    conn.commit()
    conn.close()
    return {"reset": True}
