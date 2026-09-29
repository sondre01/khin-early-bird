import hashlib
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class JobItem:
    id: str
    source: str
    title: str
    company: str
    location: str
    work_type: str  # Remote, Hybrid, On-site, Unknown
    job_type: str   # Internship, Regular
    role_category: str  # software_engineering, web_development, it_tech_support, data_analytics, data_engineering, data_science, qa_testing
    salary: str
    description: str
    apply_url: str
    posted_date: str
    extracted_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def generate_job_id(source: str, title: str, company: str, apply_url: str = "") -> str:
    """Generates a stable, unique hash for deduplication based on title, company, and source"""
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    clean_company = re.sub(r'[^a-zA-Z0-9]', '', company.lower())
    clean_source = source.lower().strip()
    
    # If URL contains a distinct job ID, incorporate that
    url_id_match = re.search(r'(\d{8,})', apply_url)
    suffix = url_id_match.group(1) if url_id_match else ""
    
    unique_key = f"{clean_source}:{clean_company}:{clean_title}:{suffix}"
    return hashlib.sha256(unique_key.encode('utf-8')).hexdigest()[:16]

class BaseScraper:
    def __init__(self, name: str):
        self.name = name

    def scrape(self, keyword: str, location: str = "Philippines", limit: int = 15) -> List[JobItem]:
        raise NotImplementedError("Subclasses must implement scrape()")
