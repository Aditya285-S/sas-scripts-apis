from fastapi import FastAPI, HTTPException, Body
from dotenv import load_dotenv
import requests
import json
import os
from urllib.parse import quote

load_dotenv()

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
PROJECT_ID = os.getenv("GITLAB_PROJECT_ID")  # For commit (required)
PROJECT_PATH = os.getenv("GITLAB_PROJECT_PATH")  # For readable URL
BASE_API_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com/api/v4")

if not GITLAB_TOKEN or not PROJECT_ID or not PROJECT_PATH:
    raise ValueError("❌ Missing one of: GITLAB_TOKEN, GITLAB_PROJECT_ID, or GITLAB_PROJECT_PATH in .env file")

HEADERS = {
    "PRIVATE-TOKEN": GITLAB_TOKEN,
    "Content-Type": "application/json"
}

BASE_URL = f"{BASE_API_URL}/projects/{PROJECT_ID}/repository/files"

app = FastAPI(title="GitLab Job Manager API")


# --- UTILITIES ---
def load_jobs(config_path="gitlab_jobs.json"):
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading jobs: {e}")


def get_job_by_id(job_id: str):
    jobs = load_jobs()
    for job in jobs:
        if job.get("job_id") == job_id:
            encoded_file_path = quote(job["script_path"], safe="")
            job["file_raw_url"] = (
                f"{BASE_API_URL}/projects/{quote(PROJECT_PATH, safe='')}/repository/files/{encoded_file_path}/raw?ref=main"
            )
            return job
    raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")


def file_exists(file_path: str, branch: str = "main") -> bool:
    encoded_path = quote(file_path, safe="")
    url = f"{BASE_URL}/{encoded_path}?ref={branch}"
    response = requests.get(url, headers=HEADERS)
    return response.status_code == 200


def push_to_gitlab(file_path: str, content: str, commit_message: str):
    encoded_path = quote(file_path, safe="")
    url = f"{BASE_URL}/{encoded_path}"

    payload = {
        "branch": "main",
        "content": content,
        "commit_message": commit_message
    }

    if file_exists(file_path, "main"):
        response = requests.put(url, headers=HEADERS, data=json.dumps(payload))
        action = "updated"
    else:
        response = requests.post(url, headers=HEADERS, data=json.dumps(payload))
        action = "created"

    if response.status_code not in [200, 201]:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return {
        "status": "success",
        "action": action,
        "file_path": file_path
    }


# --- ROUTES ---
@app.get("/jobs")
def list_jobs():
    return load_jobs()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    return get_job_by_id(job_id)


@app.post("/jobs/{job_id}/commit")
def commit_job(job_id: str, payload: dict = Body(...)):
    """
    Commit a specific job to GitLab.
    Request body must include:
    {
        "content": "file content to commit",
        "commit_message": "optional commit message"
    }
    """
    job = get_job_by_id(job_id)
    content = payload.get("content")
    if not content:
        raise HTTPException(status_code=400, detail="Missing 'content' in request body")
    
    commit_message = payload.get("commit_message", f"Commit job logs for {job['script_name']}")
    
    # --- NEW: Build GitLab path ---
    file_path_in_gitlab = f"sas/optimized/{job['script_name']}"
    
    result = push_to_gitlab(file_path_in_gitlab, content, commit_message)
    
    return {
        "job_id": job["job_id"],
        "file_path": result["file_path"],
        "action": result["action"],
        "status": "✅ success"
    }
