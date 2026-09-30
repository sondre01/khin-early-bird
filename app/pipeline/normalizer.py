import re
from typing import Dict, Any
from app.scrapers.base import JobItem
from app.utils.url_resolver import resolve_apply_url

class JobNormalizer:
    @staticmethod
    def normalize(job: JobItem) -> Dict[str, Any]:
        """Cleans, normalizes, categorizes, and resolves apply URL for a scraped job item."""
        d = job.to_dict()
        
        # Clean title
        title = re.sub(r'\s+', ' ', d["title"]).strip()
        d["title"] = title
        
        # Clean company
        company = re.sub(r'\s+', ' ', d["company"]).strip()
        d["company"] = company
        
        # Clean location
        location = re.sub(r'\s+', ' ', d["location"]).strip()
        d["location"] = location or "Philippines"
        
        # Segregation: Internship vs Regular
        lower_title = title.lower()
        lower_desc = d.get("description", "").lower()
        
        is_internship = any(
            re.search(rf"\b{term}\b", lower_title)
            for term in ["intern", "internship", "ojt", "trainee", "practicum", "apprentice", "student"]
        ) or any(
            re.search(rf"\b{term}\b", lower_desc[:200])
            for term in ["internship", "ojt", "on the job training"]
        )
        
        d["job_type"] = "Internship" if is_internship else "Regular"
        
        # Work type classification
        combined_text = f"{title} {location} {d.get('description', '')}".lower()
        if "remote" in combined_text or "work from home" in combined_text or "wfh" in combined_text:
            d["work_type"] = "Remote"
        elif "hybrid" in combined_text or "flexible" in combined_text:
            d["work_type"] = "Hybrid"
        else:
            d["work_type"] = "On-site"
            
        # Refine role category
        d["role_category"] = JobNormalizer.detect_role_category(title, d.get("description", ""))
        
        # Sanitize and resolve apply URL to prevent 404s
        d["apply_url"] = resolve_apply_url(d.get("source", ""), title, company, d.get("apply_url"))
        
        return d

    @staticmethod
    def detect_role_category(title: str, description: str) -> str:
        text = f"{title} {description[:300]}".lower()
        
        if any(w in text for w in ["qa", "quality assurance", "software tester", "test automation", "qc analyst"]):
            return "qa_testing"
        if any(w in text for w in ["data engineer", "etl", "data pipeline", "database developer", "snowflake engineer", "data warehouse"]):
            return "data_engineering"
        if any(w in text for w in ["data scientist", "machine learning", "ai engineer", "deep learning", "computer vision", "yolo"]):
            return "data_science"
        if any(w in text for w in ["data analyst", "bi analyst", "business intelligence", "analytics specialist", "power bi"]):
            return "data_analytics"
        if any(w in text for w in ["it support", "technical support", "helpdesk", "desktop support", "sysadmin", "system administrator", "it admin", "it operations", "active directory", "snipe-it"]):
            return "it_tech_support"
        if any(w in text for w in ["web developer", "frontend", "front-end", "react", "vue", "javascript developer", "ui developer"]):
            return "web_development"
        if any(w in text for w in ["software", "backend", "full stack", "fullstack", "python developer", "c#", "java developer", "programmer", "software engineer"]):
            return "software_engineering"
            
        return "software_engineering"
