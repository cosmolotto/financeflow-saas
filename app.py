from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
import uuid

app = FastAPI(title="FinanceFlow SaaS")

SECRET = "SUPER_SECRET_KEY"

users = {}
admins = {}
jobs = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# AUTH
# -----------------------------

@app.post("/signup")
def signup(username: str, password: str):

    if username in users:
        raise HTTPException(status_code=400, detail="User exists")

    users[username] = password

    return {"status": "user created"}


@app.post("/login")
def login(username: str, password: str):

    if users.get(username) != password:
        raise HTTPException(status_code=401, detail="invalid login")

    token = jwt.encode({"user": username}, SECRET)

    return {"token": token}


# -----------------------------
# ADMIN SYSTEM
# -----------------------------

@app.post("/admin/create")
def create_admin(master_key: str, username: str, password: str):

    if master_key != "MASTER_ADMIN_KEY":
        raise HTTPException(status_code=403, detail="not authorized")

    admins[username] = password

    return {"status": "admin created"}


@app.post("/admin/login")
def admin_login(username: str, password: str):

    if admins.get(username) != password:
        raise HTTPException(status_code=401, detail="invalid admin")

    token = jwt.encode({"admin": username}, SECRET)

    return {"token": token}


# -----------------------------
# AI VIDEO GENERATION JOB
# -----------------------------

@app.post("/video/generate")
def generate_video(prompt: str):

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "prompt": prompt,
        "status": "processing"
    }

    return {
        "job_id": job_id,
        "status": "started"
    }


@app.get("/video/status/{job_id}")
def video_status(job_id: str):

    if job_id not in jobs:
        raise HTTPException(status_code=404)

    return jobs[job_id]


# -----------------------------
# HEALTH CHECK
# -----------------------------

@app.get("/")
def root():
    return {"status": "FinanceFlow SaaS running"}
