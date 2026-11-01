from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from database import get_db_connection

router = APIRouter()

class ContactIn(BaseModel):
    name: str = Field(..., min_length=1)
    ph_number: str = Field(..., pattern=r"^\d{10,15}$")
    enable: Optional[bool] = True

class ContactOut(BaseModel):
    id: int
    name: str
    ph_number: str
    enable: bool

@router.get("/contacts", response_model=List[ContactOut])
def list_contacts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, ph_number, enable FROM contacts ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [ContactOut(id=r["id"], name=r["name"], ph_number=r["ph_number"], enable=bool(r["enable"])) for r in rows]

@router.get("/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, ph_number, enable FROM contacts WHERE id = %s", (contact_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactOut(id=row["id"], name=row["name"], ph_number=row["ph_number"], enable=bool(row["enable"]))

@router.post("/contacts", status_code=201, response_model=ContactOut)
def create_contact(payload: ContactIn):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO contacts (name, ph_number, enable) VALUES (%s, %s, %s) RETURNING id",
        (payload.name, payload.ph_number, int(payload.enable)),
    )
    contact_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return ContactOut(id=contact_id, name=payload.name, ph_number=payload.ph_number, enable=bool(payload.enable))

@router.put("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, payload: ContactIn):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM contacts WHERE id = %s", (contact_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")
    cur.execute(
        "UPDATE contacts SET name = %s, ph_number = %s, enable = %s WHERE id = %s",
        (payload.name, payload.ph_number, int(payload.enable), contact_id),
    )
    conn.commit()
    conn.close()
    return ContactOut(id=contact_id, name=payload.name, ph_number=payload.ph_number, enable=bool(payload.enable))

@router.patch("/contacts/{contact_id}/enable", response_model=ContactOut)
def patch_enable(contact_id: int, enable: bool):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, ph_number FROM contacts WHERE id = %s", (contact_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")
    cur.execute("UPDATE contacts SET enable = %s WHERE id = %s", (int(enable), contact_id))
    conn.commit()
    conn.close()
    return ContactOut(id=row["id"], name=row["name"], ph_number=row["ph_number"], enable=enable)

@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM contacts WHERE id = %s", (contact_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")
    cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
    conn.commit()
    conn.close()
    return {}
