from fastapi import FastAPI, HTTPException
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
    """Load all job definitions from JSON file."""
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading jobs: {e}")


def get_job_by_id(job_id: str):
    """Retrieve a single job by ID and add the GitLab raw file URL."""
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
    """Check if a file already exists in GitLab repo."""
    encoded_path = quote(file_path, safe="")
    url = f"{BASE_URL}/{encoded_path}?ref={branch}"
    response = requests.get(url, headers=HEADERS)
    return response.status_code == 200


def push_to_gitlab(job: dict):
    """Create or update a file in GitLab repo using project ID."""
    encoded_path = quote(job["script_path"], safe="")
    url = f"{BASE_URL}/{encoded_path}"

    payload = {
        "branch": "main",
        "content": job["logs"],
        "commit_message": f"Commit job logs for {job['script_name']}"
    }

    if file_exists(job["script_path"], "main"):
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
        "file_path": job["script_path"]
    }


# --- ROUTES ---
@app.get("/jobs")
def list_jobs():
    """List all available GitLab jobs."""
    return load_jobs()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Get a single job by its ID (adds GitLab raw URL)."""
    return get_job_by_id(job_id)


@app.post("/jobs/{job_id}/commit")
def commit_job(job_id: str):
    """Commit a specific job to GitLab (create/update file)."""
    job = get_job_by_id(job_id)
    result = push_to_gitlab(job)
    return {
        "job_id": job["job_id"],
        "file_path": result["file_path"],
        "action": result["action"],
        "status": "✅ success"
    }
