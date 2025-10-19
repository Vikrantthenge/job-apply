from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
from datetime import datetime
import pandas as pd
import json
import requests

app = FastAPI()

# Mount static folder for logo and assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Homepage route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- Resume Parsing ---
@app.post("/parse_resume")
async def parse_resume(resume: UploadFile):
    return {"keywords": ["Python", "SQL", "Streamlit", "Machine Learning", "Power BI"]}

# --- Bullet Rewriting ---
@app.post("/rewrite_bullet")
async def rewrite_bullet(bullet: str = Form(...), tone: str = Form(...)):
    rewritten = f"• Spearheaded demand forecasting models, driving a 12% profitability surge — {tone.capitalize()} delivery for recruiter impact."
    return {"rewritten_bullet": rewritten}

# --- Job Search (Live API) ---
@app.post("/search_jobs")
async def search_jobs(
    keywords: str = Form(...),
    location: str = Form(...),
    num_pages: int = Form(...),
    min_salary_lpa: int = Form(...),
    include_unspecified: bool = Form(True)
):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": "ak_2pqbtupzn1901zx5c9vx3qmt14hx8uxsn4cc54bausvqkcy",
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": f"{keywords} in {location}",
        "num_pages": num_pages
    }

    response = requests.get(url, headers=headers, params=params)
    jobs = response.json().get("data", [])

    filtered = []
    for job in jobs:
        min_salary = job.get("job_min_salary", 0)
        max_salary = job.get("job_max_salary", 0)
        if include_unspecified or min_salary >= min_salary_lpa * 100000:
            salary_str = (
                f"₹{min_salary // 100000}–{max_salary // 100000} LPA"
                if min_salary and max_salary else "Not disclosed"
            )
            filtered.append({
                "title": job["job_title"],
                "company": job["employer_name"],
                "location": job.get("job_city", "Unknown"),
                "salary": salary_str,
                "apply_link": job["job_apply_link"]
            })

    return {"jobs": filtered}

# --- Auto Apply + Logging ---
@app.post("/auto_apply")
async def auto_apply(
    resume: UploadFile,
    jobs: List[str] = Form(...),
    keyword: str = Form(...),
    location: str = Form(...)
):
    timestamp = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    log_df = pd.DataFrame({
        "Company": jobs,
        "Applied On": [timestamp] * len(jobs),
        "Keyword": [keyword] * len(jobs),
        "Location": [location] * len(jobs)
    })
    csv_data = log_df.to_csv(index=False)
    return {
        "status": "Applied to all jobs",
        "timestamp": timestamp,
        "log": log_df.to_dict(),
        "csv": csv_data
    }

# --- Drift Monitor ---
@app.post("/drift_monitor")
async def drift_monitor(old_csv: UploadFile, new_csv: UploadFile):
    df_old = pd.read_csv(old_csv.file)
    df_new = pd.read_csv(new_csv.file)
    old_freq = df_old["Job Title"].value_counts().head(10)
    new_freq = df_new["Job Title"].value_counts().head(10)
    drift_df = pd.DataFrame({"Old": old_freq, "New": new_freq}).fillna(0)
    return {"drift": drift_df.to_dict()}from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
from datetime import datetime
import pandas as pd
import json

app = FastAPI()

# Mount static folder for logo and assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Homepage route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- Resume Parsing ---
@app.post("/parse_resume")
async def parse_resume(resume: UploadFile):
    return {"keywords": ["Python", "SQL", "Streamlit", "Machine Learning", "Power BI"]}

# --- Bullet Rewriting ---
@app.post("/rewrite_bullet")
async def rewrite_bullet(bullet: str = Form(...), tone: str = Form(...)):
    rewritten = f"• Spearheaded demand forecasting models, driving a 12% profitability surge — {tone.capitalize()} delivery for recruiter impact."
    return {"rewritten_bullet": rewritten}

# --- Job Search ---
@app.post("/search_jobs")
async def search_jobs(
    keywords: str = Form(...),
    location: str = Form(...),
    num_pages: int = Form(...),
    min_salary_lpa: int = Form(...),
    include_unspecified: bool = Form(True)
):
    min_salary_in_inr = min_salary_lpa * 100000
    jobs = [
        {"title": "Data Analyst", "company": "ABC Corp", "location": location, "salary": "₹25 LPA", "apply_link": "https://example.com/apply"},
        {"title": "BI Developer", "company": "XYZ Ltd", "location": location, "salary": "Not disclosed", "apply_link": "https://example.com/apply"}
    ]
    filtered = [job for job in jobs if include_unspecified or job["salary"] != "Not disclosed"]
    return {"jobs": filtered}

# --- Auto Apply + Logging ---
@app.post("/auto_apply")
async def auto_apply(
    resume: UploadFile,
    jobs: List[str] = Form(...),
    keyword: str = Form(...),
    location: str = Form(...)
):
    timestamp = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    log_df = pd.DataFrame({
        "Company": jobs,
        "Applied On": [timestamp] * len(jobs),
        "Keyword": [keyword] * len(jobs),
        "Location": [location] * len(jobs)
    })
    csv_data = log_df.to_csv(index=False)
    return {
        "status": "Applied to all jobs",
        "timestamp": timestamp,
        "log": log_df.to_dict(),
        "csv": csv_data
    }

# --- Drift Monitor ---
@app.post("/drift_monitor")
async def drift_monitor(old_csv: UploadFile, new_csv: UploadFile):
    df_old = pd.read_csv(old_csv.file)
    df_new = pd.read_csv(new_csv.file)
    old_freq = df_old["Job Title"].value_counts().head(10)
    new_freq = df_new["Job Title"].value_counts().head(10)
    drift_df = pd.DataFrame({"Old": old_freq, "New": new_freq}).fillna(0)
    return {"drift": drift_df.to_dict()}