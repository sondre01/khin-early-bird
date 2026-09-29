import json
import logging
from pathlib import Path
from typing import Dict, Any
import pypdf
from app.config import RESUME_DIR, DATA_DIR, USER_NAME, USER_EMAIL, USER_PHONE, USER_LOCATION

logger = logging.getLogger(__name__)

CACHE_FILE = DATA_DIR / "extracted_resumes.json"

STRUCTURED_PROFILE = {
    "name": USER_NAME,
    "email": USER_EMAIL,
    "phone": USER_PHONE,
    "location": USER_LOCATION,
    "education": {
        "degree": "Bachelor of Science in Computer Engineering",
        "institution": "Rizal Technological University (RTU)",
        "graduated": "July 2026",
        "honors": "Dean's List Academic Honor Awardee (CGWA: 1.73)",
        "specialization": "Data Architecture, Embedded IoT Systems, Applied Machine Learning"
    },
    "certifications": [
        "Associate Data Engineer | DataCamp (ID: DEA0017096233010)",
        "Associate Data Analyst | DataCamp",
        "Data Fundamentals | IBM SkillsBuild & TESDA",
        "Python Essentials 1 | Cisco Networking Academy & OpenEDG"
    ],
    "work_experience": [
        {
            "role": "IT Administrator and Operation / IT QA Intern",
            "company": "Staff Domain",
            "period": "January 2026 - June 2026",
            "highlights": [
                "Migrated 20,000+ hardware and software assets from unstandardized spreadsheets into Snipe-IT relational database, reducing provisioning latency by 80%",
                "Executed functional QA testing, regression verification, and full bug lifecycle tracking for internal ITMS modules in Jira",
                "Engineered modular automation scripts in PowerShell and CLI for workstation diagnostics and maintenance",
                "Configured enterprise endpoints and identity access using Active Directory and Azure AD; resolved networking tickets across TCP/IP, DNS/DHCP, and VPN interfaces"
            ]
        }
    ],
    "projects": [
        {
            "title": "Four-in-One Vital Sign Sensor Kiosk with AI & IoT (Capstone)",
            "tech": "Python, Flask, MySQL, React.js, YOLOv11, XGBoost, Tailscale VPN, PyTest",
            "description": "3-tier backend service streaming telemetry from 5 biomedical sensors; automated risk assessment and posture compliance."
        },
        {
            "title": "Social Media Analytics Automated ETL Pipeline",
            "tech": "Python, PostgreSQL, Pandas, Docker, cron",
            "description": "End-to-end data pipeline extracting multi-platform metrics, schema normalization, batch ingestion into PostgreSQL with Docker."
        },
        {
            "title": "Web-Based Ticketing & Queue Analytics System",
            "tech": "Python, Flask, SQL, JavaScript, Vercel",
            "description": "Full-stack support ticketing engine with RBAC, automated issue routing, and real-time queue analytics dashboards."
        },
        {
            "title": "AI Kilo Bot",
            "tech": "Python, Raspberry Pi, YOLO, Roboflow, HX711 Sensor Fusion",
            "description": "Intelligent digital scale merging computer vision object classification with strain-gauge load-cell telemetry for automated item checkout."
        }
    ],
    "skills": {
        "programming": ["Python", "SQL", "JavaScript", "TypeScript", "C#", "Java", "C++", "Bash", "PowerShell", "HTML/CSS"],
        "data_engineering_and_analytics": ["PostgreSQL", "MySQL", "Snowflake", "ETL/ELT Pipelines", "Pandas", "Power BI", "Tableau", "Query Optimization", "Schema Design"],
        "machine_learning_ai": ["XGBoost", "YOLOv11", "Roboflow", "PyTorch", "Computer Vision", "Statistical Hypothesis Testing"],
        "software_web_dev": ["React.js", "Flask", "Node.js", "REST APIs", "Docker", "Git/GitHub", "Vercel", "Supabase"],
        "it_support_networking": ["Active Directory", "Azure AD", "Snipe-IT", "Datto RMM", "TCP/IP", "DNS/DHCP", "VPN Setup", "Windows/Linux/macOS Support", "Workstation Provisioning"],
        "qa_testing": ["Functional QA Testing", "Regression Verification", "Jira Bug Lifecycle", "PyTest", "Test Case Documentation", "ISO/IEC 25010"]
    }
}


def load_raw_resume_texts() -> Dict[str, str]:
    """Reads all PDF resumes from documents/resume or loads from cache"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read cache {CACHE_FILE}: {e}")

    results = {}
    if RESUME_DIR.exists():
        for pdf_path in RESUME_DIR.glob("*.pdf"):
            try:
                reader = pypdf.PdfReader(str(pdf_path))
                text = "\n".join([page.extract_text() or "" for page in reader.pages])
                results[pdf_path.name] = text
            except Exception as e:
                logger.error(f"Error reading {pdf_path}: {e}")

    if results:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return results


def get_candidate_profile_context(role_category: str = None) -> str:
    """Returns a tailored markdown summary of Khin Andrei Gamboa's profile for the AI evaluator"""
    skills_block = []
    for cat, items in STRUCTURED_PROFILE["skills"].items():
        skills_block.append(f"- **{cat.replace('_', ' ').title()}**: {', '.join(items)}")

    certs = "\n".join([f"- {c}" for c in STRUCTURED_PROFILE["certifications"]])
    projects = "\n".join([f"- **{p['title']}** ({p['tech']}): {p['description']}" for p in STRUCTURED_PROFILE["projects"]])
    experience = "\n".join([
        f"- **{exp['role']} @ {exp['company']}** ({exp['period']}):\n  " + "\n  ".join([f"• {h}" for h in exp["highlights"]])
        for exp in STRUCTURED_PROFILE["work_experience"]
    ])

    return f"""
Candidate: {STRUCTURED_PROFILE['name']}
Email: {STRUCTURED_PROFILE['email']} | Location: {STRUCTURED_PROFILE['location']}
Education: {STRUCTURED_PROFILE['education']['degree']} - {STRUCTURED_PROFILE['education']['institution']} (Graduated: {STRUCTURED_PROFILE['education']['graduated']})
Honors: {STRUCTURED_PROFILE['education']['honors']}
Certifications:
{certs}

Work & Internship Experience:
{experience}

Selected Capstone & Technical Projects:
{projects}

Technical Skills Inventory:
{chr(10).join(skills_block)}
Target Roles: Software Engineer / Web Developer, IT Tech Support / Admin, Data Analyst / Data Engineer / Data Scientist, QA Tester.
Eligible for: Internships, Graduate Programs, Junior / Associate / Regular Full-Time Roles.
""".strip()
