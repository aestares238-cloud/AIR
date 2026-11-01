import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

DB_URI = os.environ.get("SUPABASE_URL")

if not DB_URI and ENV_FILE.exists():
    with open(ENV_FILE, "r") as f:
        for line in f:
            cleaned_line = line.strip()
            if not cleaned_line or cleaned_line.startswith("#"):
                continue
            if "=" in cleaned_line:
                key, val = cleaned_line.split("=", 1)
                if key.strip() == "SUPABASE_URL":
                    DB_URI = val.strip()
                    break

if not DB_URI:
    CONNECTION_FILE = BASE_DIR / "supabase_connection.txt"
    if CONNECTION_FILE.exists():
        with open(CONNECTION_FILE, "r") as f:
            DB_URI = f.read().strip()

if not DB_URI:
    raise ValueError("Database connection string not found.")

def get_db_connection():
    """
    Establish and return a connection to the PostgreSQL database.
    Forces the session timezone to Asia/Manila so Render and Supabase align.
    """
    conn = psycopg2.connect(DB_URI)
    conn.cursor_factory = RealDictCursor
    
    # FIX: Force timezone for ALL queries on this connection
    cur = conn.cursor()
    cur.execute("SET TIME ZONE 'Asia/Manila';")
    cur.close()
    
    return conn
