from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
import re
import json
import html as html_lib
from database import get_db_connection
from services import ac_manager
from services.auth import get_admin_from_token

router = APIRouter()

TEMPLATES_DIR = Path("templates/pages")


# --- AC list: the pages used to hard-code AC1..AC6; they now follow the AC manager --------------
# Replaces any run of  <option value="ACn">ACn</option>  and of  <button ... data-ac="ACn">ACn</button>
# with the current units (value = fixed device code, text = dashboard label AC1, AC2, ...).
_OPT_RUN = re.compile(r'((?:[ \t]*<option value="AC\d+">AC\d+</option>[ \t]*\r?\n?)+)')
_BTN_RUN = re.compile(r'((?:[ \t]*<button class="[^"]*" data-ac="AC\d+">\s*AC\d+\s*</button>[ \t]*\r?\n?)+)')
_BTN_CLASS = re.compile(r'<button class="([^"]*)" data-ac="AC\d+">')


def _inject_ac_units(page_html: str) -> str:
    units = ac_manager.cached_units(get_db_connection)
    if not units:
        return page_html  # database not reachable or no units yet: keep the page as written

    def options(m):
        indent = re.match(r"[ \t]*", m.group(1)).group(0)
        return "".join(
            f'{indent}<option value="{html_lib.escape(u["code"])}">{html_lib.escape(u["label"])}</option>\n' for u in units
        )

    def buttons(m):
        indent = re.match(r"[ \t]*", m.group(1)).group(0)
        cls = _BTN_CLASS.search(m.group(1)).group(1)
        return "".join(
            f'{indent}<button class="{cls}" data-ac="{html_lib.escape(u["code"])}">\n'
            f'{indent}    {html_lib.escape(u["label"])}\n{indent}</button>\n'
            for u in units
        )

    page_html = _OPT_RUN.sub(options, page_html)
    page_html = _BTN_RUN.sub(buttons, page_html)
    labels = json.dumps({u["code"]: u["label"] for u in units}).replace("</", "<\\/")
    tag = f"<script>window.AC_LABELS = {labels};</script>"
    return page_html.replace("</head>", tag + "\n</head>", 1) if "</head>" in page_html else page_html


def _read_template(filename: str) -> str:
    p = TEMPLATES_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    content = p.read_text(encoding="utf-8")

    # Simple recursive parser to resolve <!-- INCLUDE filename.html --> comments
    def resolve_includes(text: str) -> str:
        pattern = r"<!--\s*INCLUDE\s+([A-Za-z0-9_-]+\.html)\s*-->"
        def replace(match):
            inc_file = match.group(1)
            inc_path = TEMPLATES_DIR / inc_file
            if inc_path.exists():
                return resolve_includes(inc_path.read_text(encoding="utf-8"))
            return f"<!-- Include error: {inc_file} not found -->"
        return re.sub(pattern, replace, text)

    resolved = resolve_includes(content)
    if 'rel="icon"' not in resolved and 'rel="shortcut icon"' not in resolved:
        favicon_html = '\n    <link rel="icon" type="image/png" href="/assets/xd/logo.png?v=3">\n    <link rel="shortcut icon" type="image/png" href="/assets/xd/logo.png?v=3">'
        if "<head>" in resolved:
            resolved = resolved.replace("<head>", f"<head>{favicon_html}", 1)
        elif "<HEAD>" in resolved:
            resolved = resolved.replace("<HEAD>", f"<HEAD>{favicon_html}", 1)

    if filename != "login.html":
        try:
            resolved = _inject_ac_units(resolved)
        except Exception as e:
            print(f"[PAGES] could not inject the AC list into {filename}: {e}", flush=True)

    return resolved


@router.get("/pages", response_class=HTMLResponse)
def pages_index(request: Request):
    token = request.cookies.get("admin_session")
    if not get_admin_from_token(token):
        return RedirectResponse(url="/pages/login", status_code=303)
    return HTMLResponse(_read_template("index.html"))


@router.get("/pages/{name}", response_class=HTMLResponse)
def page(name: str, request: Request):
    # Restrict page name to safe characters to avoid path traversal
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise HTTPException(status_code=400, detail="Invalid page name")
    
    # Check session
    token = request.cookies.get("admin_session")
    is_authenticated = get_admin_from_token(token) is not None

    if name == "login":
        # If already logged in, skip login page and go straight to the Control Panel
        if is_authenticated:
            return RedirectResponse(url="/", status_code=303)
    else:
        # Enforce authentication for all other pages
        if not is_authenticated:
            return RedirectResponse(url="/pages/login", status_code=303)
            
    return HTMLResponse(_read_template(f"{name}.html"))
