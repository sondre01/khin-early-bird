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
        "specialization": "Software Systems, IT Infrastructure, Applied Machine Learning, and Data Architecture"
    },
    "certifications": [
        "Associate Data Engineer | DataCamp (ID: DEA0017096233010) - August 2026",
        "Associate Data Analyst | DataCamp",
        "Data Fundamentals | IBM SkillsBuild & TESDA - July 2026",
        "Python Essentials 1 | Cisco Networking Academy & OpenEDG - July 2026"
    ],
    "work_experience": [
        {
            "role": "IT Developer Intern & IT Administrator and Operation",
            "company": "Staff Domain",
            "period": "January 2026 - June 2026",
            "highlights": [
                "Programmed modular automation tooling and CLI scripts in PowerShell to automate workstation configurations, environment setup, policy configuration, and routine systems diagnostics.",
                "Developed automated ETL data migration scripts mapping 20,000+ unstandardized asset records into centralized Snipe-IT relational database structures with zero downtime, reducing provisioning latency by 80%.",
                "Built and deployed custom scripting solutions interfacing with Active Directory and Azure AD / Microsoft Entra ID APIs, automating credential and endpoint provisioning workflows.",
                "Streamlined end-to-end workstation onboarding by provisioning, installing operating systems, and deploying enterprise tools to guarantee day-one readiness for new personnel.",
                "Diagnosed and resolved Tier-1 and Tier-2 hardware, software, and connectivity disruptions, maintaining high first-contact resolution; performed IP parameter configurations, ping tests, DNS/DHCP validation, and enterprise VPN support (Tailscale, OpenVPN).",
                "Contributed to internal ITMS modules by debugging backend issues, writing regression scripts, and tracking full bug lifecycles in Jira, partnering with DevOps to validate release fixes."
            ]
        }
    ],
    "projects": [
        {
            "title": "Web-Based Ticketing & Queue Analytics System",
            "tech": "Python, Flask, SQL, JavaScript, React.js, Vercel",
            "description": "Full-stack support ticketing engine featuring relational SQL storage, role-based access control (RBAC), and automated issue routing pipelines; engineered RESTful APIs in Flask serving real-time analytics payloads under 150ms, decreasing support triage latency by 40%."
        },
        {
            "title": "Four-in-One Vital Sign Kiosk System with AI & IoT",
            "tech": "Python, Flask, MySQL, React.js, Docker, PyTest, YOLOv11, XGBoost",
            "description": "Architected a 3-tier backend service in Flask and designed relational MySQL schemas to ingest, index, and query health telemetry from 5 serial sensor streams with sub-second latency; engineered and deployed ML anomaly detection pipelines with responsive React.js UI/UX."
        },
        {
            "title": "Social Media Analytics Automated ETL Pipeline",
            "tech": "Python, PostgreSQL, Pandas, Docker, cron",
            "description": "Engineered modular Python services to ingest and normalize external API payloads, ensuring error-handling resilience across 10,000+ transaction batches; containerized with Docker and scheduled execution with cron."
        },
        {
            "title": "AI Kilo Bot Embedded App",
            "tech": "Python, Raspberry Pi, YOLO, Roboflow, Sensor Fusion",
            "description": "Developed multi-threaded software integrating live camera feeds with strain-gauge telemetry for automated checkout transactions; optimized inference pipeline down to 65ms per cycle on edge hardware."
        },
        {
            "title": "Enterprise Telemetry Kiosk & Secure Networking",
            "tech": "Tailscale Mesh VPN, Linux (Ubuntu/Debian), Python",
            "description": "Architected and secured remote deployment telemetry communication across distributed endpoints utilizing Tailscale mesh VPN and encrypted protocols, maintaining continuous uptime across remote Linux terminals."
        }
    ],
    "skills": {
        "programming": ["Python", "JavaScript", "TypeScript", "SQL", "C#", "C++", "Java", "Bash", "PowerShell", "HTML/CSS"],
        "full_stack_web_dev": ["Flask", "React.js", "Node.js", "RESTful APIs", "JSON", "Tailwind CSS", "Vercel", "Supabase"],
        "databases_data_engineering": ["PostgreSQL", "MySQL", "Supabase", "Snowflake", "DBeaver", "ETL/ELT Pipelines", "Pandas", "Power BI", "Tableau", "Query Optimization", "Relational Modeling"],
        "machine_learning_ai": ["XGBoost", "YOLOv11", "Roboflow", "PyTorch", "Computer Vision", "Statistical Hypothesis Testing", "Edge Inference", "Sensor Fusion"],
        "systems_it_operations": ["Active Directory", "Azure AD / Entra ID", "Snipe-IT Asset Management", "Windows Server", "Linux (Ubuntu/Debian)", "Workstation Provisioning", "ITSM", "Jira Service Management"],
        "networking_security": ["TCP/IP", "DNS/DHCP", "VPN Setup (Tailscale, OpenVPN)", "LAN/WAN Diagnostics", "Subnetting", "Ping Tests"],
        "qa_devops_tooling": ["Functional QA Testing", "Regression Verification", "Jira Bug Lifecycle", "PyTest", "Postman", "Docker", "Git/GitHub", "CI/CD Pipelines", "ISO/IEC 25010"]
    }
}


def load_raw_resume_texts(force_refresh: bool = False) -> Dict[str, str]:
    """Reads all PDF resumes from documents/resume or loads from cache if up-to-date."""
    if CACHE_FILE.exists() and not force_refresh:
        try:
            cache_mtime = CACHE_FILE.stat().st_mtime
            pdf_files = list(RESUME_DIR.glob("*.pdf")) if RESUME_DIR.exists() else []
            # Cache is valid only if all resume PDFs are older than or equal to the cache timestamp
            if pdf_files and all(p.stat().st_mtime <= cache_mtime for p in pdf_files):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read cache {CACHE_FILE}: {e}")

    results = {}
    if RESUME_DIR.exists():
        for pdf_path in sorted(RESUME_DIR.glob("*.pdf")):
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
            logger.info(f"Successfully refreshed extracted resumes cache ({len(results)} files).")
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
