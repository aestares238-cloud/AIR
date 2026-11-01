# Summary of Changes — June 20, 2026

This document lists all the database migrations, rule engine updates, bug fixes, testing procedures, and documentation changes performed today to support historical data and water-cooled chiller anomalies.

---

## 1. Environment & Dependencies
*   Created a Linux-compatible virtual environment (`.venv`) under `raspi/` to replace the non-executable Windows-based virtual environment structure.
*   Installed all required packages (`pandas`, `openpyxl`, `psycopg2-binary`, `SQLAlchemy`, etc.) to run the data processing and database scripts.

## 2. Historical Data Migration (ETL)
*   **Source Data**: Analyzed 4 Excel spreadsheets containing chiller sensor logs in `migrations/`:
    *   `FEB-DATA-2026.xlsx`
    *   `March-Data.xlsx`
    *   `APRIL-DATA-2026.xlsx`
    *   `JUNE-DATE-2026.xlsx`
*   **Database Table**: Created the `historical_data` table in Supabase with columns for pressures, temperatures, and currents.
*   **ETL Script**: Developed and executed [migrate_historical_data.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/migrate_historical_data.py) which parses spreadsheet rows starting from Row 3 (where row index maps to the day of the month) and performs idempotent upserts into Supabase.
*   **Result**: Migrated **86 clean, structured records** ranging from `2026-02-01` to `2026-06-05`.

## 3. Data Auditing & Operational Health Check
*   Developed [check_data_health.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/check_data_health.py) to audit the historical records for anomalies.
*   **Findings**: Discovered **27 anomalous records** in the historical database:
    *   **19 Critical Overloaded Current** events where the compressor motor drew up to `52.0A` (rated max is `45.0A`).
    *   **8 High Inefficient Heat Exchange** events where the compressor drew substantial load but the condenser water inlet and outlet temperatures were identical (`0.0°C` difference).
*   **Impact**: Highlighted model contamination risks; advised filtering out these 27 anomalous rows to keep only the healthy 59 days for Isolation Forest training.

## 4. Rule Engine Updates
*   **Threshold Rules**: Appended rules to `RULES` in [rule_engine.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/services/rule_engine.py) to support the water-cooled chiller loop:
    *   Suction Pressure (normal: 0.30 - 0.60 MPa)
    *   Discharge Pressure (normal: 1.40 - 2.20 MPa)
    *   Water Inlet Temperature (normal: 20.0 - 35.0 °C)
    *   Water Outlet Temperature (normal: 21.0 - 40.0 °C)
    *   Compressor Amperes (normal: 10.0 - 45.0 A)
    *   AC Supply Outlet Temp (normal: 12.0 - 24.0 °C)
*   **Virtual Calculated Sensors**: Refactored `analyze_with_rules` to compute virtual sensor variables:
    *   `water_temp_diff`: Checks water temperature difference when active. Flags `temp_diff <= 0.2 °C` as inefficient heat exchange.
    *   `compressor_pressure_diff`: Checks pressure split when active. Flags pressure splits `< 0.30 MPa` as potential valve leaks.

## 5. Back-Migration of Alarms
*   Developed and executed [generate_historical_alerts.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/generate_historical_alerts.py) to back-run all 86 historical rows.
*   **Result**: Checked all historical rows and generated **36 back-dated alert records** in the `alerts` database table, matching the exact timestamps of the historical faults.

## 6. Recommended Action Summary Bug Fix
*   **Issue**: Summaries of alerts were truncated to `"Action: 1."` instead of displaying the actual first recommendation sentence because splitting on `". "` split the string at the numbered list prefix (e.g. `"1. "`).
*   **Fix**: Rewrote the sentence-splitting parser in [anomaly_reciever.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/services/anomaly_reciever.py), [test_alert_inject.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/test_alert_inject.py), and test scripts to inspect if a segment is a list digit, and correctly join it with the subsequent sentence if so.

## 7. Mock Chiller Anomaly Injection
*   Created [test_water_anomaly_inject.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/test_water_anomaly_inject.py) to simulate an extremely unhealthy water-cooled AC day.
*   Verified that the updated rule engine successfully triggered 6 rules (overall severity: `Critical`) and stored a properly formatted summary warning in Supabase (Alert ID `201`).

## 8. Documentation Updates
*   Updated [supabase_migration.md](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/documentation/supabase_migration.md) to document the schema, ETL script, and historical alert back-runs.
*   Updated [hybrid_anomaly_detection.md](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/documentation/hybrid_anomaly_detection.md) to document all new rules, virtual calculations, flow diagrams, and testing scripts.
