from typing import List, Dict
import requests
from services.contacts_api import get_db_connection
from services.traccar_setup_api import get_traccar_setup, DEFAULT_TRACCAR_SMS_URL


def _get_traccar_config() -> Dict[str, str]:
    setup = get_traccar_setup()
    sms_url = (setup.get("sms_url") or "").strip() or DEFAULT_TRACCAR_SMS_URL
    api_key = (setup.get("api_key") or "").strip()
    return {"sms_url": sms_url, "api_key": api_key}

def _get_enabled_numbers() -> List[str]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT ph_number FROM contacts WHERE enable = 1")
    rows = cur.fetchall()
    conn.close()
    return [r["ph_number"] for r in rows]

def send_sms(text: str = "TEST MESSAGE") -> Dict:
    """Send `text` to all enabled contact numbers via Traccar SMS endpoint.

    Sends one POST per number with payload {"to": number, "message": text}.
    Returns a summary dict with per-number results.
    """
    numbers = _get_enabled_numbers()
    if not numbers:
        return {"ok": False, "error": "no enabled contacts", "results": []}

    traccar_cfg = _get_traccar_config()
    sms_url = traccar_cfg["sms_url"]
    api_key = traccar_cfg["api_key"]
    
    # We don't need to manually set Content-Type; using `json=` parameter in requests does it automatically.
    headers = {}
    if api_key:
        # Traccar SMS gateway expects the token directly, not as a Bearer token
        headers["Authorization"] = api_key

    results = []
    any_ok = False
    for num in numbers:
        # Use the `text` parameter passed to the function instead of hardcoding "TEST MESSAGE"
        payload = {"to": num, "message": text} 
        try:
            # FIX: Use `json=payload` instead of `data=payload`
            resp = requests.post(sms_url, json=payload, headers=headers, timeout=10)
            print(resp)
            ok = 200 <= resp.status_code < 300
            
            results.append({"to": num, "ok": ok, "status_code": resp.status_code, "response": resp.text})
            print(f"Result for {num}: {resp.status_code} - {resp.text}")
            
            if ok:
                any_ok = True
        except Exception as e:
            results.append({"to": num, "ok": False, "error": str(e)})

    return {"ok": any_ok, "results": results}
