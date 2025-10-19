"""
job-apply-app.py - Job Bot (FastAPI) with Jooble (hardcoded key) + OpenAI rewrite + optional Google Sheets sync

Features:
- Job search via Jooble free API (hardcoded key)
- Job results page with "Apply Now", "Mark as Applied", and "Auto-Apply" (simulated)
- Applied jobs persisted to a local JSON file and visualized via Plotly on dashboard
- Resume bullet rewriting using OpenAI (gpt-4o-mini) — requires OPENAI_API_KEY env var
- Optional Google Sheets sync if GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_URL env vars are set
- Self-creates minimal templates in ./templates and mounts ./static

Run:
  export OPENAI_API_KEY="sk-"
  uvicorn job-apply-app --reload --host 0.0.0.0 --port 8000
"""

import os
import json
import base64
import uuid
from datetime import datetime
from typing import List, Optional

import requests
import pandas as pd
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from plotly import io as plotly_io
import plotly.express as px

# OpenAI client
import openai

# Google Sheets libs (optional)
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GS_ENABLED = True
except Exception:
    GS_ENABLED = False

# ---------------- CONFIG ----------------
# Hardcoded Jooble API key (user requested hardcode)
JOOBLE_API_KEY = "f3610c6c-eeb8-4742-bec8-eee2a995315f"

# OpenAI key must be supplied via env for security (you accepted cost/usage)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Optional Google Sheets settings
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "").strip()

# Files / paths
TEMPLATES_DIR = "templates"
STATIC_DIR = "static"
APPLIED_STORE = "applied_jobs.json"

# OpenAI model to use
OPENAI_MODEL = "gpt-4o-mini"

# Create app
app = FastAPI(title="Job Bot — Jooble + OpenAI")

# Ensure directories exist
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static and templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Configure OpenAI
if not OPENAI_API_KEY:
    # we do not raise here because user might want to use only job fetching/dashboard.
    print("WARNING: OPENAI_API_KEY not set. Resume rewriter will not function until you set OPENAI_API_KEY.")
else:
    openai.api_key = OPENAI_API_KEY

# ---------- Helper functions ----------

def jooble_search(keywords: str, location: str, page: int = 1, limit: int = 20):
    """
    Call Jooble API (free tier). Returns list of job dicts with keys:
    title, company, location, salary, apply_link
    """
    url = f"https://jooble.org/api/{JOOBLE_API_KEY}"
    payload = {
        "keywords": keywords,
        "location": location,
        "page": page,
        # Jooble supports params such as "salary" etc in advanced usage
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("jobs", [])
    except Exception as e:
        # If Jooble fails, return an empty list (or simulated sample)
        print("Jooble fetch error:", e)
        jobs = []

    results = []
    for j in jobs[:limit]:
        results.append({
            "title": j.get("title") or j.get("position") or "Unknown",
            "company": j.get("company") or j.get("employer") or "Unknown",
            "location": j.get("location") or j.get("city") or "Unknown",
            "salary": j.get("salary") or j.get("compensation") or "Not disclosed",
            "apply_link": j.get("link") or j.get("url") or "#"
        })
    # If Jooble returned nothing, provide a small simulated sample so UI isn't empty
    if not results:
        results = [
            {"title": "Data Analyst", "company": "Acme Analytics", "location": "Bengaluru", "salary": "₹10–15 LPA", "apply_link": "https://example.com/1"},
            {"title": "Business Intelligence Analyst", "company": "InsightWorks", "location": "Mumbai", "salary": "Not disclosed", "apply_link": "https://example.com/2"},
        ]
    return results

def append_applied_record(rec: dict):
    """
    Append a record (dictionary) to local JSON store.
    """
    try:
        arr = []
        if os.path.exists(APPLIED_STORE):
            with open(APPLIED_STORE, "r", encoding="utf-8") as f:
                arr = json.load(f)
        arr.append(rec)
        with open(APPLIED_STORE, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to append applied record:", e)

def load_applied_df():
    if not os.path.exists(APPLIED_STORE):
        return pd.DataFrame(columns=["Applied On", "Company", "Job Title", "Location", "Keyword"])
    try:
        with open(APPLIED_STORE, "r", encoding="utf-8") as f:
            arr = json.load(f)
        df = pd.DataFrame(arr)
        return df
    except Exception as e:
        print("Failed to load applied store:", e)
        return pd.DataFrame(columns=["Applied On", "Company", "Job Title", "Location", "Keyword"])

def get_gs_client():
    """
    Create a gspread client using GOOGLE_SERVICE_ACCOUNT_JSON (string JSON or base64).
    """
    if not GS_ENABLED:
        raise RuntimeError("gspread/oauth not installed in environment.")
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured.")
    creds_json = GOOGLE_SERVICE_ACCOUNT_JSON
    # try base64 decode if looks encoded
    if "\n" not in creds_json and len(creds_json) > 200:
        try:
            decoded = base64.b64decode(creds_json)
            creds_json = decoded.decode("utf-8")
        except Exception:
            pass
    creds = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    client = gspread.authorize(credentials)
    return client

# ---------- Templates (auto-create minimal templates) ----------
INDEX_HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Job Bot — Home</title>
<style>body{font-family:Arial;max-width:900px;margin:24px auto;color:#222} .card{border:1px solid #eee;padding:16px;border-radius:8px;margin-bottom:12px} .btn{background:#8B0000;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none} .muted{color:#666}</style>
</head>
<body>
  <h1>🧭 Job Bot</h1>
  <div class="card">
    <h3>Search Jobs (Jooble)</h3>
    <form action="/job_results" method="post">
      Keywords: <input name="keywords" value="Data Analyst" /> &nbsp;
      Location: <input name="location" value="India" /> &nbsp;
      Page: <input type="number" name="page" value="1" min="1" /> &nbsp;
      <button class="btn" type="submit">Search</button>
    </form>
    <p class="muted">Jooble key is hardcoded for quick testing.</p>
  </div>

  <div class="card">
    <h3>Resume Bullet Rewriter (OpenAI)</h3>
    <p><a class="btn" href="/rewrite">Open Rewriter</a></p>
    <p class="muted">Requires OPENAI_API_KEY env var to be set.</p>
  </div>

  <div class="card">
    <h3>Dashboard</h3>
    <p><a class="btn" href="/dashboard">View Applied Jobs Dashboard</a></p>
  </div>

  <footer style="margin-top:24px;color:#777">Built with FastAPI • Jooble • OpenAI (optional) • Plotly</footer>
</body>
</html>
"""

JOB_RESULTS_HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Job Results</title>
<style>body{font-family:Arial;max-width:1000px;margin:16px auto} .card{border:1px solid #eee;padding:12px;border-radius:8px;margin-bottom:10px} .job-title{font-weight:700} .btn{background:#8B0000;color:#fff;padding:6px 10px;border-radius:6px;text-decoration:none} .apply{background:#0066cc;color:#fff;padding:6px 10px;border-radius:6px;text-decoration:none}</style>
</head>
<body>
  <p><a href="/">← Back Home</a></p>
  <h2>Results for "{{ keywords }}" in "{{ location }}"</h2>
  <form action="/auto_apply" method="post" enctype="multipart/form-data" style="margin-bottom:12px">
    <input type="hidden" name="search_id" value="{{ search_id }}" />
    Upload Resume (optional): <input type="file" name="resume" />
    <button class="btn" type="submit">🚀 Auto-Apply to All (simulated)</button>
  </form>

  {% for job in jobs %}
    <div class="card">
      <div class="job-title">{{ job.title }}</div>
      <div>{{ job.company }} • {{ job.location }} • {{ job.salary }}</div>
      <p style="margin-top:8px;">
        <a class="apply" href="{{ job.apply_link }}" target="_blank">Apply Now</a>
        <form style="display:inline" action="/manual_apply" method="post">
          <input type="hidden" name="title" value="{{ job.title }}" />
          <input type="hidden" name="company" value="{{ job.company }}" />
          <input type="hidden" name="location" value="{{ job.location }}" />
          <button style="margin-left:8px;padding:6px 10px;">Mark as Applied</button>
        </form>
      </p>
    </div>
  {% endfor %}

  <p><a href="/dashboard">View Dashboard →</a></p>
</body>
</html>
"""

DASHBOARD_HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Applied Dashboard</title>
<style>body{font-family:Arial;max-width:1100px;margin:20px auto}.card{border:1px solid #eee;padding:12px;border-radius:8px;margin-bottom:12px}.muted{color:#666} table{width:100%;border-collapse:collapse} th,td{padding:8px;border-bottom:1px solid #f2f2f2;}</style>
</head>
<body>
  <p><a href="/">← Back Home</a></p>
  <h2>📊 Applied Jobs Dashboard</h2>

  <div class="card">
    <h3>Applied Jobs</h3>
    {% if applied_table %}
      {{ applied_table | safe }}
    {% else %}
      <p class="muted">No applied jobs yet.</p>
    {% endif %}
  </div>

  <div class="card">
    <h3>Visualizations</h3>
    {% if roles_plot %}
      <h4>Top Roles</h4>
      {{ roles_plot | safe }}
    {% endif %}
    {% if city_plot %}
      <h4>Applications by City</h4>
      {{ city_plot | safe }}
    {% endif %}
  </div>

  <div class="card">
    <h3>Sync</h3>
    <form action="/sync_sheet" method="post">
      <button type="submit" class="btn">Sync to Google Sheets (optional)</button>
    </form>
    <p class="muted">Google configured: {{ google_ok }}</p>
  </div>
</body>
</html>
"""

REWRITE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Rewrite Bullet</title></head>
<body style="font-family:Arial;max-width:900px;margin:24px auto">
  <p><a href="/">← Back</a></p>
  <h2>Resume Bullet Rewriter (OpenAI)</h2>
  <form method="post" action="/rewrite" >
    <textarea name="bullet" rows="4" cols="80" placeholder="Enter bullet to rewrite">Improved forecasting by building models that reduced error.</textarea><br/>
    Tone:
    <select name="tone">
      <option value="assertive">assertive</option>
      <option value="formal">formal</option>
      <option value="friendly">friendly</option>
    </select>
    <button type="submit">Rewrite</button>
  </form>

  {% if rewritten %}
    <hr/>
    <h3>Rewritten Bullet</h3>
    <div style="background:#f6f6f6;padding:12px;border-radius:6px">{{ rewritten }}</div>
  {% endif %}
</body>
</html>
"""

# write templates if not exist
templates_map = {
    "index.html": INDEX_HTML,
    "job_results.html": JOB_RESULTS_HTML,
    "dashboard.html": DASHBOARD_HTML,
    "rewrite.html": REWRITE_HTML
}
for fname, content in templates_map.items():
    full = os.path.join(TEMPLATES_DIR, fname)
    if not os.path.exists(full):
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

# ---------- In-memory search store ----------
SEARCH_STORE = {}  # search_id -> list of job dicts

# ---------- Routes ----------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/job_results", response_class=HTMLResponse)
async def job_results(request: Request, keywords: str = Form(...), location: str = Form(...), page: int = Form(1)):
    jobs = jooble_search(keywords, location, page=page, limit=40)
    search_id = str(uuid.uuid4())
    SEARCH_STORE[search_id] = jobs
    return templates.TemplateResponse("job_results.html", {"request": request, "jobs": jobs, "keywords": keywords, "location": location, "search_id": search_id})

@app.post("/manual_apply")
async def manual_apply(title: str = Form(...), company: str = Form(...), location: str = Form(...)):
    rec = {
        "Applied On": datetime.now().strftime("%d-%b-%Y %I:%M %p"),
        "Company": company,
        "Job Title": title,
        "Location": location,
        "Keyword": ""
    }
    append_applied_record(rec)
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/auto_apply")
async def auto_apply(request: Request, search_id: str = Form(...), resume: Optional[UploadFile] = File(None)):
    jobs = SEARCH_STORE.get(search_id)
    if not jobs:
        raise HTTPException(status_code=400, detail="Search expired or invalid.")
    ts = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    for j in jobs:
        rec = {
            "Applied On": ts,
            "Company": j.get("company"),
            "Job Title": j.get("title"),
            "Location": j.get("location"),
            "Keyword": ""
        }
        append_applied_record(rec)
    # optionally save resume file to static for reference
    if resume:
        fname = f"resume_{uuid.uuid4().hex[:8]}_{resume.filename}"
        saved = os.path.join(STATIC_DIR, fname)
        with open(saved, "wb") as f:
            f.write(await resume.read())
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    df = load_applied_df()
    applied_table = None
    roles_plot = None
    city_plot = None
    if not df.empty:
        applied_table = df.to_html(index=False, classes="applied-table", escape=False)
        # roles pie
        if "Job Title" in df.columns:
            r = df["Job Title"].value_counts().reset_index()
            r.columns = ["Role", "Count"]
            fig_r = px.pie(r, names="Role", values="Count", title="Top Roles")
            roles_plot = plotly_io.to_html(fig_r, include_plotlyjs="cdn", full_html=False)
        # city bar
        if "Location" in df.columns:
            c = df["Location"].value_counts().reset_index()
            c.columns = ["City", "Count"]
            fig_c = px.bar(c, x="City", y="Count", title="Applications by City")
            city_plot = plotly_io.to_html(fig_c, include_plotlyjs=False, full_html=False)
    google_ok = bool(GOOGLE_SHEET_URL and GOOGLE_SERVICE_ACCOUNT_JSON and GS_ENABLED)
    return templates.TemplateResponse("dashboard.html", {"request": request, "applied_table": applied_table, "roles_plot": roles_plot, "city_plot": city_plot, "google_ok": google_ok})

@app.post("/sync_sheet")
async def sync_sheet():
    """
    Sync local applied jobs to Google Sheets (requires GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_URL env vars)
    """
    if not (GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_URL):
        raise HTTPException(status_code=400, detail="Google Sheets credentials or URL not configured.")
    if not GS_ENABLED:
        raise HTTPException(status_code=500, detail="gspread / oauth libraries not available.")
    df = load_applied_df()
    if df.empty:
        return {"status": "no_data", "message": "No applied jobs to sync."}
    try:
        client = get_gs_client()
        sh = client.open_by_url(GOOGLE_SHEET_URL)
        ws = sh.sheet1
        rows = [df.columns.tolist()] + df.fillna("").values.tolist()
        ws.clear()
        ws.append_rows(rows)
        ws.update_acell("A1", f"Last synced: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}")
        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets sync failed: {e}")

@app.get("/rewrite", response_class=HTMLResponse)
async def rewrite_get(request: Request):
    return templates.TemplateResponse("rewrite.html", {"request": request})

@app.post("/rewrite", response_class=HTMLResponse)
async def rewrite_post(request: Request, bullet: str = Form(...), tone: str = Form("assertive")):
    """
    Use OpenAI to rewrite the provided bullet.
    Requires OPENAI_API_KEY set in environment.
    """
    if not OPENAI_API_KEY:
        rewritten = "[OpenAI API key not configured. Set OPENAI_API_KEY environment variable to use rewriter.]"
        return templates.TemplateResponse("rewrite.html", {"request": request, "rewritten": rewritten})

    prompt = (
        f"Rewrite the following resume bullet to be concise, recruiter-friendly, and impactful. "
        f"Use measurable language if possible. Keep it one line.\n\n"
        f"Tone: {tone}\n"
        f"Bullet: {bullet}\n\n"
        f"Return only the rewritten bullet."
    )
    try:
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional resume writer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=120,
        )
        rewritten = resp.choices[0].message["content"].strip()
    except Exception as e:
        rewritten = f"[OpenAI error: {e}]"

    return templates.TemplateResponse("rewrite.html", {"request": request, "rewritten": rewritten})

# ---------- Endpoints for quick testing ----------
@app.get("/_health")
async def health():
    return {"status": "ok", "jooble_key_present": bool(JOOBLE_API_KEY)}

# ----------------- End of file -----------------
