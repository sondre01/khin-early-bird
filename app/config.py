import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if os.getenv("VERCEL"):
    DATA_DIR = Path("/tmp")
else:
    DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "documents"
RESUME_DIR = DOCS_DIR / "resume"
ENV_FILE = PROJECT_ROOT / ".env"

# Ensure data dir exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load environment
load_dotenv(ENV_FILE)

# User info
USER_NAME = os.getenv("USER_NAME", "Khin Andrei Gamboa")
USER_EMAIL = os.getenv("USER_EMAIL", "gamboa.khinandrei@gmail.com")
USER_PHONE = os.getenv("USER_PHONE", "+63 992 421 5130")
USER_LOCATION = os.getenv("USER_LOCATION", "Pasig City, Philippines")
DEFAULT_TARGET_LOCATION = os.getenv("DEFAULT_TARGET_LOCATION", "Metro Manila, Philippines")
FILTER_NCR_ONLY = os.getenv("FILTER_NCR_ONLY", "true").lower() in ("1", "true", "yes")

# AI Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Email Settings
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "gamboa.khinandrei@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_NOTIFICATIONS_ENABLED = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() in ("1", "true", "yes")

# Scheduler Settings
DAILY_RUN_TIME = os.getenv("DAILY_RUN_TIME", "08:00")
AUTO_RUN_ON_STARTUP = os.getenv("AUTO_RUN_ON_STARTUP", "false").lower() in ("1", "true", "yes")

# Web Server
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DB_PATH = DATA_DIR / "early_bird.db"

# Role Categories & Target Search Keywords
TARGET_CATEGORIES = {
    "software_engineering": {
        "label": "Software Engineering",
        "keywords": [
            "Junior Software Engineer", "Associate Software Engineer", "Software Engineer",
            "Python Developer", "Full Stack Developer", "Backend Engineer"
        ]
    },
    "web_development": {
        "label": "Web Development",
        "keywords": [
            "Web Developer", "Frontend Developer", "React Developer",
            "Junior Web Developer", "JavaScript Developer"
        ]
    },
    "it_tech_support": {
        "label": "IT Tech Support & Operations",
        "keywords": [
            "IT Tech Support", "IT Support Specialist", "IT Administrator",
            "Helpdesk Technician", "Desktop Support", "Technical Support Representative"
        ]
    },
    "data_analytics": {
        "label": "Data Analytics",
        "keywords": [
            "Data Analyst", "Junior Data Analyst", "Associate Data Analyst",
            "BI Analyst", "Business Intelligence Analyst"
        ]
    },
    "data_engineering": {
        "label": "Data Engineering",
        "keywords": [
            "Data Engineer", "Junior Data Engineer", "Associate Data Engineer",
            "ETL Developer", "Data Pipeline Engineer"
        ]
    },
    "data_science": {
        "label": "Data Science & AI",
        "keywords": [
            "Junior Data Scientist", "Data Scientist", "Machine Learning Engineer",
            "AI Engineer", "Computer Vision Intern"
        ]
    },
    "qa_testing": {
        "label": "QA & Software Testing",
        "keywords": [
            "QA Engineer", "Quality Assurance Analyst", "Software QA Tester",
            "Junior QA Engineer", "Manual Tester"
        ]
    }
}

# Segregation Types
JOB_TYPES = ["Internship", "Regular"]

def update_env_variable(key: str, value: str):
    """Update a specific key in the .env file and in os.environ"""
    os.environ[key] = value
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}=") or line.strip() == key:
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        lines = new_lines
    else:
        lines = [f"{key}={value}\n"]
        
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
