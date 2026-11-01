# Supabase Migration Guide

This document outlines the process for migrating the existing local SQLite database (`telemetry.db`) to a Supabase PostgreSQL instance.

## Overview
The migration involves extracting all schema definitions and data from SQLite and importing them into Supabase.

## Steps

1. **Schema Creation in Supabase**
   - We need to translate the SQLite schema for the `telemetry` table and other setup tables (`ac_setup`, `contacts`, `alerts`, `traccar_setup`, `ai_setup`) to PostgreSQL syntax.
   - Example `telemetry` table:
     ```sql
     CREATE TABLE telemetry (
         id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
         timestamp TIMESTAMPTZ DEFAULT NOW(),
         dust_sensor REAL,
         dht_temp REAL,
         dht_humidity REAL,
         vibration REAL,
         ds18b20_temp1 REAL,
         ds18b20_temp2 REAL,
         pzem_voltage REAL,
         pzem_current REAL,
         pzem_power REAL,
         pzem_energy REAL,
         pzem_frequency REAL,
         pzem_power_factor REAL,
         ac_status TEXT,
         ac_thermostat TEXT
     );
     ```

2. **Data Transfer Script**
   - Create a Python script (e.g., `scripts/migrate_to_supabase.py`) to connect to both the local SQLite database and the Supabase instance.
   - We will need to read data from SQLite in batches and insert it into Supabase to avoid memory issues.

3. **Database Connectivity Notes**
   - Ensure you connect to the Supabase connection pooler via Session Mode (port 5432) if you are encountering IPv6-only database host issues.

## Historical Data Migration

To import historical spreadsheets (such as February, March, April, and June 2026 data) into Supabase, a dedicated pipeline was introduced:

1. **Table Creation**
   The table `historical_data` was created in Supabase with the following schema:
   ```sql
   CREATE TABLE historical_data (
       date DATE PRIMARY KEY,
       compressor_suction_pressure TEXT,
       compressor_discharge_pressure TEXT,
       water_inlet_temp_c REAL,
       water_inlet_pressure_mpa REAL,
       water_outlet_temp_c REAL,
       water_outlet_pressure_mpa REAL,
       fan_amperes REAL,
       compressor_amperes REAL,
       ac_inlet_temp_in REAL,
       ac_inlet_temp_out REAL,
       ac_outlet_temp REAL
   );
   ```

2. **Migration Script**
   Run the migration script [migrate_historical_data.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/migrate_historical_data.py) to read all `.xlsx` files from the `migrations/` directory and perform idempotent upserts into Supabase:
   ```bash
   python scripts/migrate_historical_data.py
   ```
   *Note: Row indices map to days of the month, i.e., Row 3 maps to Day 1.*

3. **Historical Alert Back-Run**
   Run [generate_historical_alerts.py](file:///home/gericandmorty/Desktop/Clients/Airbnbrrr/main/raspi/scripts/generate_historical_alerts.py) to process all historical records through the rule engine and back-date the resulting alarms into the `alerts` table:
   ```bash
   python scripts/generate_historical_alerts.py
   ```
