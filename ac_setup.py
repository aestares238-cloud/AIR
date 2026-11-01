from database import get_db_connection

def get_ac_setup():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT ac_status, ac_thermostat, data_gathering_mode, data_gathering_unit FROM ac_setup LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {
            "ac_status": "Not Set",
            "ac_thermostat": "Not Set",
            "data_gathering_mode": "telemetry",
            "data_gathering_unit": "AC2"
        }
    return {
        "ac_status": row.get("ac_status", "Not Set"),
        "ac_thermostat": row.get("ac_thermostat", "Not Set"),
        "data_gathering_mode": row.get("data_gathering_mode", "telemetry"),
        "data_gathering_unit": row.get("data_gathering_unit", "AC2")
    }

def update_ac_setup(ac_status: str, ac_thermostat: str, data_gathering_mode: str = None, data_gathering_unit: str = None):
    conn = get_db_connection()
    cur = conn.cursor()
    if data_gathering_mode is not None and data_gathering_unit is not None:
        cur.execute(
            "UPDATE ac_setup SET ac_status = %s, ac_thermostat = %s, data_gathering_mode = %s, data_gathering_unit = %s",
            (ac_status, ac_thermostat, data_gathering_mode, data_gathering_unit)
        )
    else:
        cur.execute("UPDATE ac_setup SET ac_status = %s, ac_thermostat = %s", (ac_status, ac_thermostat))
    conn.commit()
    conn.close()
