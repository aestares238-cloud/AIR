import bcrypt
import secrets
from datetime import datetime, timedelta
from database import get_db_connection

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def generate_session(username: str) -> tuple[str, str]:
    token = secrets.token_hex(32)
    expiry = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "DELETE FROM admin_sessions WHERE username = %s AND access_token_expiry < %s",
            (username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    except Exception:
        pass

    cur.execute(
        "INSERT INTO admin_sessions (username, access_token, access_token_expiry) VALUES (%s, %s, %s)",
        (username, token, expiry)
    )
    conn.commit()
    conn.close()
    return token, expiry

def clear_session(token: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM admin_sessions WHERE access_token = %s", (token,))
    conn.commit()
    conn.close()

def get_admin_from_token(token: str) -> dict | None:
    if not token:
        return None
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT username, access_token_expiry FROM admin_sessions WHERE access_token = %s",
        (token,)
    )
    session_row = cur.fetchone()
    
    if not session_row:
        conn.close()
        return None
        
    try:
        expiry_str = str(session_row["access_token_expiry"])
        # Strip timezone markers just in case
        if "+" in expiry_str: expiry_str = expiry_str.split("+")[0]
        if "." in expiry_str: expiry_str = expiry_str.split(".")[0]
        expiry_str = expiry_str.replace("T", " ").strip()
        
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        
        if now > expiry:
            cur.execute("DELETE FROM admin_sessions WHERE access_token = %s", (token,))
            conn.commit()
            conn.close()
            return None
    except Exception as e:
        print(f"Session time parse error: {e}")
        conn.close()
        return None
        
    cur.execute("SELECT id, username FROM admin WHERE username = %s", (session_row["username"],))
    admin_row = cur.fetchone()
    conn.close()
    
    if not admin_row:
        return None
        
    return {
        "id": admin_row["id"],
        "username": admin_row["username"]
    }
