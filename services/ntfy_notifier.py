"""
ntfy push notifications for AirBnBrrr.

One alert event = ONE short notification: the worst problems in plain words, then what to do.
The full details (all readings, every step) are on the Alerts page.

Configure with environment variables on Render:
    NTFY_TOPIC    required. Use a long random name, public topics are readable by anyone who
                  knows the name, e.g. AirBnrr_alien_test_code_k8x2m9qv4t
    NTFY_SERVER   optional, default https://ntfy.sh (set it if you self-host)
    NTFY_TOKEN    optional access token, for protected topics
    APP_URL       optional, your site address; tapping the notification opens the Alerts page
Uses only the standard library, so there is nothing new to install.
"""
import os
import urllib.request

from services import action_guide

SHOW_PROBLEMS = 3     # problems listed in the notification
MAX_BYTES = 1500


def finding_text(f):
    """One plain line for a rule-engine finding (dict) or a plain string."""
    if isinstance(f, str):
        return f.strip()
    if isinstance(f, dict):
        return action_guide.plain_line(f)
    return str(f)


_SEV = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def build_problems(critical_reasons, findings, ml):
    """Plain problem lines, worst first, no duplicates (the AI note goes last).

    The rule engine uses the same limits as the instant safety alerts, so when it has findings the raw
    limit lines would only repeat them; they are used only when the rule engine found nothing.
    """
    ordered = sorted(findings or [], key=lambda f: -_SEV.get(f.get("severity") if isinstance(f, dict) else None, 0))
    items = [finding_text(f) for f in ordered] if ordered else list(critical_reasons or [])
    line = action_guide.ml_line(ml)
    if line:
        items.append(line)
    seen, out = set(), []
    for it in items:
        key = it.lower()
        if it and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def build_message(unit_title, is_critical, problems, readings=None, actions=None):
    """Return (title, body). Title is plain ASCII because it travels in an HTTP header."""
    title = (f"STOP: {unit_title}" if is_critical else f"Check: {unit_title}").encode("ascii", "replace").decode("ascii")
    ai = [p for p in problems if p.startswith("The AI")]
    real = [p for p in problems if not p.startswith("The AI")]
    lines = [f"- {p}" for p in real[:SHOW_PROBLEMS]]
    if len(real) > SHOW_PROBLEMS:
        lines.append(f"+ {len(real) - SHOW_PROBLEMS} more on the Alerts page")
    if ai:
        lines.append(ai[0])
    if not lines:
        lines.append("The AC is acting differently from its normal.")
    if actions:
        lines += ["", "Do this now:"] + [f"{i}. {a}" for i, a in enumerate(actions, start=1)]
    body = "\n".join(lines)
    return title, body.encode("utf-8")[:MAX_BYTES].decode("utf-8", "ignore")


def _post(title, body, priority, tags):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("[NTFY] NTFY_TOPIC is not set, skipping notification", flush=True)
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": str(priority), "Tags": tags}
    if os.environ.get("APP_URL"):
        headers["Click"] = os.environ["APP_URL"].rstrip("/") + "/pages/alerts"
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NTFY_TOKEN"]
    req = urllib.request.Request(f"{server}/{topic}", data=body.encode("utf-8"), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            ok = 200 <= resp.status < 300
        print(f"[NTFY] sent '{title}'" if ok else f"[NTFY] unexpected status {resp.status}", flush=True)
        return ok
    except Exception as e:
        print(f"[NTFY] send failed: {e}", flush=True)
        return False


def send_alert(unit_title, is_critical, problems, readings=None, actions=None):
    title, body = build_message(unit_title, is_critical, problems, readings, actions)
    return _post(title, body, 5 if is_critical else 4, "rotating_light" if is_critical else "warning")


def send_test():
    return _post("AirBnBrrr test", "ntfy is connected. Real alerts look like this: the worst problems in plain words, then what to do.", 3, "white_check_mark")
