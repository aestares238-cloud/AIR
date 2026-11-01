# Connecting FastAPI to Supabase

This document explains how the FastAPI backend connects to the Supabase database.

## Dependencies
You will need to install the appropriate PostgreSQL drivers and Supabase client:
```bash
pip install supabase psycopg2-binary python-dotenv
```

## Environment Variables
Create a `.env` file in the project root to store your Supabase credentials securely:
```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
```

## Connection Logic
Replace the `get_db_connection()` function in `main.py` with logic that connects to Supabase. You can either use the REST API via the `supabase-py` client or use direct PostgreSQL connection using `psycopg2`.

Example using `supabase-py`:
```python
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Query example
response = supabase.table('telemetry').select('*').execute()
```
