from fastapi import APIRouter
from pydantic import BaseModel
from database import get_db_connection

router = APIRouter()
DEFAULT_AI_URL = "https://api.cerebras.ai/v1/chat/completions"
DEFAULT_AI_MODEL = "zai-glm-4.7"

class AISetup(BaseModel):
    api_url: str = DEFAULT_AI_URL
    api_key: str = ""
    model: str = DEFAULT_AI_MODEL

def get_ai_setup() -> dict:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT api_url, api_key, model FROM ai_setup LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"api_url": DEFAULT_AI_URL, "api_key": "", "model": DEFAULT_AI_MODEL}
    return {
        "api_url": row["api_url"] or DEFAULT_AI_URL,
        "api_key": row["api_key"] or "",
        "model": row["model"] or DEFAULT_AI_MODEL,
    }

def update_ai_setup(api_url: str, api_key: str, model: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE ai_setup SET api_url = %s, api_key = %s, model = %s", (api_url, api_key, model))
    conn.commit()
    conn.close()

@router.get("/ai_setup")
def read_ai_setup():
    return get_ai_setup()

@router.post("/ai_setup")
def set_ai_setup(payload: AISetup):
    api_url = payload.api_url.strip() if payload.api_url else DEFAULT_AI_URL
    api_key = payload.api_key.strip() if payload.api_key else ""
    model = payload.model.strip() if payload.model else DEFAULT_AI_MODEL
    update_ai_setup(api_url, api_key, model)
    return {"status": "updated", "api_url": api_url, "api_key": api_key, "model": model}
