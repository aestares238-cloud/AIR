# AirBnBrrr: AI-Powered HVAC IoT Monitoring System

AirBnBrrr is an end-to-end IoT monitoring and proactive fault detection system designed specifically for Window-Type Air Conditioners. It ingests real-time telemetry from a Raspberry Pi sensor array and processes the data through a FastAPI backend to detect anomalies, generate explainable reports, and dispatch automated SMS alerts.

## Key Features

*   **IoT Telemetry Ingestion**: Receives real-time data from a custom Raspberry Pi sensor suite, including temperature, humidity, vibration, power consumption, current and voltage.
*   **Hybrid Diagnostic Pipeline**: A robust, three-layer approach to anomaly detection:
    1.  **Machine Learning (Isolation Forest, one model per AC)**: Every AC unit learns its own normal behaviour from its data in Supabase. The alert threshold is recomputed at every retrain from that unit's own recent normal readings, and the models are stored in Supabase so they survive redeploys.
    2.  **Deterministic Rule Engine**: A physics-based system that evaluates real-time data against hard-coded engineering thresholds (e.g., compressor overload, undervoltage) to provide verifiable, consistent findings.
    3.  **Generative AI (LLM)**: Queries the ultra-fast **Cerebras Inference API** using the **`zai-glm-4.7`** model (customizable via the web UI) to generate contextual diagnoses and forecasting. The backend includes a robust sanitization layer to clean markdown code blocks (```json ... ```) from LLM outputs for reliable JSON parsing.
*   **Automated SMS Alerts**: Integrates with Traccar SMS Gateway to instantly notify maintenance staff when critical faults are detected.
*   **ntfy Push Notifications**: Every alert also sends ONE ntfy notification per AC that lists all the problems found (hard limits, rule-engine findings and what the model found odd).
*   **AC Manager**: Add, rename or delete ACs from the dashboard; deleting an AC also removes its data and model. ACs without a custom name are shown as AC1, AC2, ... by position, so the remaining ones move up.
*   **Responsive Web Dashboard**: A clean, user-friendly interface built with Tailwind CSS to visualize telemetry data, review detailed anomaly reports side-by-side, and manage system contacts.

## Technology Stack

*   **Backend**: Python, FastAPI
*   **Database**: PostgreSQL (Supabase)
*   **Machine Learning**: scikit-learn (Isolation Forest)
*   **Frontend**: HTML, Vanilla JavaScript, Tailwind CSS, Lucide Icons
*   **Integrations**: Traccar SMS Gateway, Generative AI APIs

## Installation and Setup

### Prerequisites
*   Python 3.9+
*   PostgreSQL database (or Supabase project)

### Environment Configuration
Create a `.env` file in the root directory with the following variables:
```env
SUPABASE_URL=postgresql://[user]:[password]@[host]:[port]/[db_name]
# Add any required API keys for the Generative AI service here
```

### Setup Steps

1.  **Clone the repository and enter the directory**:
    ```bash
    git clone https://github.com/gericandmorty/AirBnbrrr.git
    cd AirBnbrrr
    ```

2.  **Create and activate a virtual environment**:
    *   Windows:
        ```cmd
        python -m venv venv
        venv\Scripts\activate
        ```
    *   macOS/Linux:
        ```bash
        python -m venv venv
        source venv/bin/activate
        ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Train the models** (creates the extra tables the first time):
    ```bash
    python train_models.py
    ```
    You can also train a single AC with the **Train now** button on the **Manage ACs** page. Until an AC has a model (it needs at least 200 readings) its alerts use the rule engine only.

### Alerts: environment variables
| Variable | Needed | Meaning |
|---|---|---|
| `SUPABASE_URL` | yes | Postgres connection string |
| `TELEMETRY_API_KEY` | recommended | A long random text. When set, only devices that send the same text in the `X-API-Key` header can post readings. The ESP32 reads it from `esp32/config.py` |
| `NTFY_TOPIC` | for ntfy | Use a long random name, e.g. `AirBnrr_alien_test_code_k8x2m9qv4t`. Public ntfy topics can be read by anyone who knows the name |
| `APP_URL` | no | Dashboard link opened when you tap the notification |
| `NTFY_SERVER` | no | Only if you self-host ntfy (default `https://ntfy.sh`) |
| `NTFY_TOKEN` | no | Access token for a protected topic |

Subscribe to the same topic in the ntfy phone app, then open `/api/ntfy/test` while logged in to send a test notification.

### ESP32 (the `esp32/` folder)
The ESP32 can post straight to your Render site over any WiFi with internet; the Raspberry Pi is not needed as a go-between. Edit `esp32/config.py` (WiFi, `SERVER_URL`, `API_KEY`, `AC_UNIT`), upload the files with Thonny, and set `TELEMETRY_API_KEY` on Render to the same text as `API_KEY`. A sensor that stops answering is sent as empty (null), which the site reports as "sensor offline".

### Per-AC models, AC manager and alerts
*   **Device code vs label**: the Pi/ESP32 sends a fixed `ac_unit` (the device code, e.g. `AC3`). The dashboard shows each AC by its position in the list (AC1, AC2, ...), so deleting one moves the others up without touching any stored data.
*   **Safety limits are per AC and editable on the web**: Manage ACs -> Safety limits. A new AC starts with the default limits (the original 1.5 HP numbers). Current, voltage and power (high) limits always alert instantly. Vibration and the two compressor temperature limits only make an alert critical when the model has already flagged the AC. The rule engine, the alert texts and the readings panel all use the AC's own limits.
*   Pages: `/pages/ac_manager` (add, delete, train, export CSV) and `/pages/ml_learning` (Model Health: how normal each AC looks over time, what it learned, how it learned, and an early-warning trend).

## Running the Application

Start the FastAPI server using Uvicorn:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The web dashboard will be available at `http://127.0.0.1:8000`.

## Architecture Overview

1.  **Raspberry Pi** collects sensor data and sends a POST request to `/telemetry`.
2.  The backend stores the raw data and scores it with that AC's own **Isolation Forest** model.
3.  If an anomaly is flagged, the data is passed to the **Rule Engine** for physics-based threshold verification.
4.  The system then queries the **LLM** for additional contextual analysis.
5.  A combined JSON report is saved, an **SMS alert** with a summary is sent to authorized contacts, and one **ntfy** notification lists every problem found on that AC.
