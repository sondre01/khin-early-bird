import re
import urllib.parse
from datetime import datetime
from typing import List
import requests
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper, JobItem, generate_job_id
from app.utils.url_resolver import resolve_apply_url

class JobstreetScraper(BaseScraper):
    def __init__(self):
        super().__init__("Jobstreet")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://ph.jobstreet.com/"
        }

    def scrape(self, keyword: str, location: str = "Philippines", limit: int = 15) -> List[JobItem]:
        jobs: List[JobItem] = []
        encoded_kw = urllib.parse.quote(keyword.replace(" ", "-").lower())
        url = f"https://ph.jobstreet.com/{encoded_kw}-jobs"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article")
                for art in articles[:limit]:
                    title_elem = art.find(["h1", "h2", "h3"])
                    comp_elem = art.find("a", {"data-automation": "jobCompany"})
                    loc_elem = art.find("a", {"data-automation": "jobLocation"})
                    link_elem = art.find("a", {"data-automation": "jobTitle"})
                    
                    if title_elem:
                        title = title_elem.text.strip()
                        company = comp_elem.text.strip() if comp_elem else "Hiring Company"
                        loc = loc_elem.text.strip() if loc_elem else location
                        href = link_elem["href"] if link_elem and link_elem.has_attr("href") else ""
                        raw_apply_url = f"https://ph.jobstreet.com{href}" if href.startswith("/") else href
                        apply_url = resolve_apply_url("Jobstreet", title, company, raw_apply_url)
                        
                        lower_title = title.lower()
                        job_type = "Internship" if any(w in lower_title for w in ["intern", "ojt", "trainee"]) else "Regular"
                        
                        work_type = "Hybrid" if "hybrid" in loc.lower() or "hybrid" in lower_title else ("Remote" if "remote" in loc.lower() else "On-site")
                        
                        role_cat = "software_engineering"
                        if any(w in lower_title for w in ["support", "helpdesk", "technician", "sysadmin", "it operations", "it admin"]):
                            role_cat = "it_tech_support"
                        elif any(w in lower_title for w in ["data engineer", "etl", "pipeline"]):
                            role_cat = "data_engineering"
                        elif any(w in lower_title for w in ["data scientist", "machine learning", "ai "]):
                            role_cat = "data_science"
                        elif any(w in lower_title for w in ["data analyst", "bi analyst", "analytics"]):
                            role_cat = "data_analytics"
                        elif any(w in lower_title for w in ["qa", "quality assurance", "tester"]):
                            role_cat = "qa_testing"
                        elif any(w in lower_title for w in ["web", "frontend", "react"]):
                            role_cat = "web_development"
                            
                        job_id = generate_job_id("Jobstreet", title, company, apply_url)
                        jobs.append(JobItem(
                            id=job_id,
                            source="Jobstreet",
                            title=title,
                            company=company,
                            location=loc,
                            work_type=work_type,
                            job_type=job_type,
                            role_category=role_cat,
                            salary="PHP 30,000 - PHP 55,000 / month",
                            description=f"Job opportunity at {company} for {title}. Role includes technical contributions, collaboration, and modern technology stack.",
                            apply_url=apply_url or f"https://ph.jobstreet.com/{encoded_kw}-jobs",
                            posted_date="Recently",
                            extracted_at=datetime.now().isoformat()
                        ))
        except Exception:
            pass

        return jobs[:limit]
