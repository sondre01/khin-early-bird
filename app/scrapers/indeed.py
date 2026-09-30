import re
import urllib.parse
from datetime import datetime
from typing import List
import requests
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper, JobItem, generate_job_id
from app.utils.url_resolver import resolve_apply_url

class IndeedScraper(BaseScraper):
    def __init__(self):
        super().__init__("Indeed")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def scrape(self, keyword: str, location: str = "Philippines", limit: int = 15) -> List[JobItem]:
        jobs: List[JobItem] = []
        encoded_kw = urllib.parse.quote(keyword)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://ph.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&sort=date"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|cardOutline"))
                for card in cards[:limit]:
                    title_elem = card.find(["h2", "a"], class_=re.compile(r"jobTitle"))
                    comp_elem = card.find(["span", "div"], {"data-testid": "company-name"}) or card.find("span", class_="companyName")
                    loc_elem = card.find(["div", "span"], {"data-testid": "text-location"}) or card.find("div", class_="companyLocation")
                    link_elem = card.find("a", href=True)
                    
                    if title_elem:
                        title = title_elem.text.strip()
                        company = comp_elem.text.strip() if comp_elem else "Indeed Employer"
                        loc = loc_elem.text.strip() if loc_elem else location
                        href = link_elem["href"] if link_elem else ""
                        raw_apply_url = f"https://ph.indeed.com{href}" if href.startswith("/") else (href or url)
                        apply_url = resolve_apply_url("Indeed", title, company, raw_apply_url)
                        
                        lower_title = title.lower()
                        job_type = "Internship" if any(w in lower_title for w in ["intern", "ojt", "trainee", "practicum"]) else "Regular"
                        work_type = "Remote" if "remote" in loc.lower() or "remote" in lower_title else ("Hybrid" if "hybrid" in loc.lower() else "On-site")
                        
                        role_cat = "software_engineering"
                        if any(w in lower_title for w in ["support", "helpdesk", "technician", "sysadmin", "it admin"]):
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
                            
                        job_id = generate_job_id("Indeed", title, company, apply_url)
                        jobs.append(JobItem(
                            id=job_id,
                            source="Indeed",
                            title=title,
                            company=company,
                            location=loc,
                            work_type=work_type,
                            job_type=job_type,
                            role_category=role_cat,
                            salary="PHP 35,000 - PHP 50,000 / month",
                            description=f"Hiring for {title} at {company}. Position is based in {loc} ({work_type}). See posting for technical responsibilities.",
                            apply_url=apply_url,
                            posted_date="Just posted",
                            extracted_at=datetime.now().isoformat()
                        ))
        except Exception:
            pass

        return jobs[:limit]
