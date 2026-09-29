import re
import urllib.parse
from datetime import datetime
from typing import List
import requests
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper, JobItem, generate_job_id

class LinkedInScraper(BaseScraper):
    def __init__(self):
        super().__init__("LinkedIn")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def scrape(self, keyword: str, location: str = "Philippines", limit: int = 15) -> List[JobItem]:
        jobs: List[JobItem] = []
        page_size = 10
        pages = max(1, (limit + page_size - 1) // page_size)
        
        for p in range(pages):
            start = p * page_size
            encoded_kw = urllib.parse.quote(keyword)
            encoded_loc = urllib.parse.quote(location)
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_kw}&location={encoded_loc}&start={start}"
            
            try:
                resp = requests.get(url, headers=self.headers, timeout=12)
                if resp.status_code != 200 or not resp.text.strip():
                    break
                
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break
                    
                for card in cards:
                    if len(jobs) >= limit:
                        break
                        
                    title_elem = card.find("h3", class_="base-search-card__title")
                    company_elem = card.find("h4", class_="base-search-card__subtitle") or card.find("a", class_="hidden-nested-link")
                    location_elem = card.find("span", class_="job-search-card__location")
                    link_elem = card.find("a", class_="base-card__full-link")
                    date_elem = card.find("time")
                    
                    if not title_elem:
                        continue
                        
                    title = title_elem.text.strip()
                    company = company_elem.text.strip() if company_elem else "Confidential Company"
                    loc = location_elem.text.strip() if location_elem else location
                    apply_url = link_elem["href"].strip() if link_elem and link_elem.has_attr("href") else f"https://www.linkedin.com/jobs/search?keywords={encoded_kw}"
                    # Clean up tracking params from URL
                    clean_url = apply_url.split("?")[0] if "?" in apply_url else apply_url
                    
                    posted_date = date_elem.text.strip() if date_elem else "Recently"
                    
                    # Detect work type
                    work_type = "On-site"
                    lower_loc = loc.lower()
                    lower_title = title.lower()
                    if "remote" in lower_loc or "remote" in lower_title:
                        work_type = "Remote"
                    elif "hybrid" in lower_loc or "hybrid" in lower_title:
                        work_type = "Hybrid"
                        
                    # Job type: Segregation between Internship and Regular
                    job_type = "Internship" if any(w in lower_title for w in ["intern", "ojt", "trainee", "practicum", "apprentice"]) else "Regular"
                    
                    # Role Category mapping
                    role_cat = "software_engineering"
                    if any(w in lower_title for w in ["support", "helpdesk", "technician", "sysadmin", "system admin", "desktop support", "it operations", "it admin"]):
                        role_cat = "it_tech_support"
                    elif any(w in lower_title for w in ["data engineer", "etl", "pipeline", "warehouse"]):
                        role_cat = "data_engineering"
                    elif any(w in lower_title for w in ["data scientist", "machine learning", "ai ", "nlp", "computer vision"]):
                        role_cat = "data_science"
                    elif any(w in lower_title for w in ["data analyst", "bi analyst", "analytics", "business intelligence"]):
                        role_cat = "data_analytics"
                    elif any(w in lower_title for w in ["qa", "quality assurance", "tester", "test automation"]):
                        role_cat = "qa_testing"
                    elif any(w in lower_title for w in ["web developer", "frontend", "front-end", "react", "vue", "angular", "ui developer"]):
                        role_cat = "web_development"
                    elif any(w in lower_title for w in ["software", "developer", "backend", "full stack", "programmer", "engineer"]):
                        role_cat = "software_engineering"

                    job_id = generate_job_id("LinkedIn", title, company, clean_url)
                    
                    # Summary description placeholder
                    desc = f"{title} at {company} located in {loc}. Opportunity for {role_cat.replace('_', ' ').title()} professionals. Visit LinkedIn posting for full details."
                    
                    item = JobItem(
                        id=job_id,
                        source="LinkedIn",
                        title=title,
                        company=company,
                        location=loc,
                        work_type=work_type,
                        job_type=job_type,
                        role_category=role_cat,
                        salary="Competitive / Not disclosed",
                        description=desc,
                        apply_url=clean_url,
                        posted_date=posted_date,
                        extracted_at=datetime.now().isoformat()
                    )
                    jobs.append(item)
                    
            except Exception as e:
                # Log and continue
                break
                
        return jobs
