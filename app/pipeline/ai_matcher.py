import os
import json
import logging
import re
from typing import Dict, Any, List
from app.config import GEMINI_API_KEY
from app.profile_loader import get_candidate_profile_context, STRUCTURED_PROFILE

logger = logging.getLogger(__name__)

class AIJobMatcher:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
        self.gemini_client = None
        
        if self.api_key and self.api_key.strip():
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.api_key.strip())
            except Exception as e:
                logger.warning(f"Could not initialize Gemini Client: {e}")

    def evaluate_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a job posting against Khin Andrei Gamboa's profile.
        Uses Gemini if API key is valid; otherwise falls back to the intelligent rule-based engine.
        """
        if self.gemini_client:
            try:
                return self._evaluate_with_gemini(job)
            except Exception as e:
                logger.warning(f"Gemini API evaluation failed ({e}). Falling back to rule-based engine.")
                return self._evaluate_with_rule_engine(job)
        else:
            return self._evaluate_with_rule_engine(job)

    def _evaluate_with_gemini(self, job: Dict[str, Any]) -> Dict[str, Any]:
        candidate_context = get_candidate_profile_context(job.get("role_category"))
        
        prompt = f"""
You are an expert technical recruiter and career advisor evaluating a job posting for Khin Andrei Gamboa.

CANDIDATE PROFILE:
{candidate_context}

JOB POSTING TO EVALUATE:
- Title: {job.get('title')}
- Company: {job.get('company')}
- Location: {job.get('location')} ({job.get('work_type')})
- Job Type: {job.get('job_type')} (Internship vs Regular)
- Category: {job.get('role_category')}
- Salary: {job.get('salary')}
- Description: {job.get('description')}

TASK:
Evaluate how well this job matches Khin Andrei Gamboa's qualifications, skills, and target roles:
1. Software Engineer / Web Developer (Python, Flask, React.js, JavaScript, SQL, REST APIs)
2. IT Tech Support / Sysadmin (Active Directory, Azure AD, Snipe-IT, Datto RMM, Troubleshooting, Networking)
3. Data Roles (Data Analyst, Data Engineer, Data Scientist - PostgreSQL, Pandas, ETL, Power BI, XGBoost, Computer Vision)
4. QA / Testing (Functional, Regression, Jira, PyTest)
Note that Khin graduated in July 2026 with a BS in Computer Engineering (Dean's List) from RTU and has 6 months of IT Admin/QA internship experience at Staff Domain.

Return ONLY a valid JSON object with this exact structure:
{{
  "match_score": <integer 0-100>,
  "match_level": "<High Match | Moderate Match | Low Match>",
  "is_applicable": <true | false>,
  "match_reasons": [
    "<specific reason 1 based on Khin's resume and this job>",
    "<specific reason 2>"
  ],
  "matched_skills": ["<skill1>", "<skill2>", ...],
  "missing_skills": ["<skill1>", "<skill2>", ...]
}}
"""
        try:
            # Try gemini-2.5-flash
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw_text = response.text.strip()
            # Clean markdown codeblocks if present
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-zA-Z]*\n", "", raw_text)
                raw_text = re.sub(r"\n```$", "", raw_text)
                
            data = json.loads(raw_text)
            data["job_id"] = job["id"]
            data["ai_model"] = "gemini-2.5-flash"
            return data
        except Exception as e:
            logger.error(f"Error calling Gemini: {e}")
            raise e

    def _evaluate_with_rule_engine(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        High-fidelity semantic rule-based evaluator matching Khin's verified qualifications.
        """
        title = job.get("title", "").lower()
        company = job.get("company", "").lower()
        loc = job.get("location", "").lower()
        desc = job.get("description", "").lower()
        job_type = job.get("job_type", "Regular")
        role_cat = job.get("role_category", "software_engineering")
        
        full_text = f"{title} {company} {loc} {desc}"
        
        # Skill vocabulary from Khin's profile
        skill_pool = {
            "Python": ["python", "flask", "fastapi", "django"],
            "SQL & Databases": ["sql", "mysql", "postgresql", "postgres", "snowflake", "database"],
            "React & Web": ["react", "react.js", "frontend", "javascript", "typescript", "html", "css"],
            "Data Engineering": ["etl", "pipeline", "pandas", "data engineering", "data migration"],
            "Data Analytics & BI": ["power bi", "tableau", "data analyst", "business intelligence", "analytics"],
            "Machine Learning / AI": ["machine learning", "xgboost", "yolo", "computer vision", "ai ", "iot"],
            "IT Support & Administration": ["active directory", "azure ad", "snipe-it", "datto", "helpdesk", "desktop support", "technical support", "troubleshooting", "workstation"],
            "Networking": ["tcp/ip", "dns", "dhcp", "vpn", "networking"],
            "QA & Testing": ["qa", "quality assurance", "pytest", "jira", "regression", "test case"],
            "DevOps & Tools": ["docker", "git", "github", "powershell", "bash", "linux", "vercel"]
        }
        
        matched_skills = []
        for display_name, aliases in skill_pool.items():
            if any(re.search(rf"\b{re.escape(alias)}\b", full_text) for alias in aliases):
                matched_skills.append(display_name)
                
        # Base scoring calculation
        score = 55
        reasons = []
        
        # Location proximity bonus (Pasig, Metro Manila, Remote, Hybrid)
        if any(p in loc for p in ["pasig", "ortigas", "taguig", "bgc", "makati", "mandaluyong", "remote", "hybrid"]):
            score += 10
            reasons.append(f"Convenient location/format: {job.get('location')} ({job.get('work_type')}).")
            
        # Role match bonus
        if role_cat in ["software_engineering", "web_development"]:
            if any(k in matched_skills for k in ["Python", "React & Web", "SQL & Databases"]):
                score += 15
                reasons.append("Strong technical alignment with Khin's Python, React.js, and Full-Stack web portfolio.")
        elif role_cat in ["data_engineering", "data_analytics", "data_science"]:
            if any(k in matched_skills for k in ["SQL & Databases", "Data Engineering", "Data Analytics & BI", "Machine Learning / AI"]):
                score += 20
                reasons.append("Directly matches Khin's DataCamp Certified Associate Data Engineer & Analyst credentials.")
        elif role_cat in ["it_tech_support"]:
            if any(k in matched_skills for k in ["IT Support & Administration", "Networking"]):
                score += 20
                reasons.append("Matches Khin's 6-month IT Admin & Operations internship at Staff Domain (Active Directory, Azure AD, Snipe-IT).")
        elif role_cat == "qa_testing":
            score += 15
            reasons.append("Matches Khin's hands-on QA testing and Jira bug tracking experience.")
            
        # Internship vs Regular experience calibration
        if job_type == "Internship":
            score += 10
            reasons.append("Candidate is highly qualified as a graduating Computer Engineering Dean's List student.")
        else:
            if any(term in title for term in ["junior", "associate", "entry", "level 1", "l1"]):
                score += 10
                reasons.append("Entry-level / Associate tier perfectly matches candidate's experience level.")
            elif any(term in title for term in ["senior", "lead", "principal", "manager"]):
                score -= 20
                
        # Skill count boost
        score += min(15, len(matched_skills) * 3)
        score = max(35, min(98, score))
        
        if score >= 80:
            level = "High Match"
        elif score >= 60:
            level = "Moderate Match"
        else:
            level = "Low Match"
            
        # Potential growth / missing skills
        missing = []
        if "cloud" in full_text and not any(k in ["Docker", "DevOps & Tools"] for k in matched_skills):
            missing.append("AWS / Cloud Architecture")
        if "agile" in full_text and "Scrum" not in matched_skills:
            missing.append("Agile / Scrum framework")
            
        if not reasons:
            reasons.append("Relevant Computer Engineering graduate opportunity matching Khin Andrei's profile.")
            
        return {
            "job_id": job["id"],
            "match_score": score,
            "match_level": level,
            "is_applicable": score >= 50,
            "match_reasons": reasons,
            "matched_skills": matched_skills or ["Computer Engineering Core", "Problem Solving"],
            "missing_skills": missing or ["Advanced Domain Specialization"],
            "ai_model": "rule-engine-v1"
        }
