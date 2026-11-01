from fastapi import APIRouter
from pydantic import BaseModel
from database import get_db_connection

router = APIRouter()
DEFAULT_TRACCAR_SMS_URL = "https://www.traccar.org/sms"

class TraccarSetup(BaseModel):
    sms_url: str = DEFAULT_TRACCAR_SMS_URL
    api_key: str = ""

def get_traccar_setup() -> dict:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT sms_url, api_key FROM traccar_setup LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"sms_url": DEFAULT_TRACCAR_SMS_URL, "api_key": ""}
    return {"sms_url": row["sms_url"], "api_key": row["api_key"] or ""}

def update_traccar_setup(sms_url: str, api_key: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE traccar_setup SET sms_url = %s, api_key = %s", (sms_url, api_key))
    conn.commit()
    conn.close()

@router.get("/traccar_setup")
def read_traccar_setup():
    return get_traccar_setup()

@router.post("/traccar_setup")
def set_traccar_setup(payload: TraccarSetup):
    sms_url = payload.sms_url.strip() if payload.sms_url else DEFAULT_TRACCAR_SMS_URL
    api_key = payload.api_key.strip() if payload.api_key else ""
    update_traccar_setup(sms_url, api_key)
    return {"status": "updated", "sms_url": sms_url, "api_key": api_key}
