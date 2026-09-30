import logging
from typing import List, Dict, Callable, Optional
from app.scrapers.base import JobItem
from app.scrapers.linkedin import LinkedInScraper
from app.scrapers.jobstreet import JobstreetScraper
from app.scrapers.indeed import IndeedScraper
from app.config import TARGET_CATEGORIES, DEFAULT_TARGET_LOCATION

logger = logging.getLogger(__name__)

class JobAggregator:
    def __init__(self):
        self.scrapers = [
            LinkedInScraper(),
            JobstreetScraper(),
            IndeedScraper()
        ]

    def run_all(
        self,
        location: str = DEFAULT_TARGET_LOCATION,
        limit_per_keyword: int = 5,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[JobItem]:
        """
        Runs all scrapers across all target roles and keywords.
        Deduplicates by Job ID and returns all collected jobs.
        """
        all_jobs: Dict[str, JobItem] = {}
        
        # Build search task list: (role_key, keyword, is_internship_focus)
        search_tasks = []
        for cat_key, cat_data in TARGET_CATEGORIES.items():
            for kw in cat_data["keywords"][:2]:  # Top 2 representative keywords per category
                search_tasks.append((cat_key, kw, False))
                
        # Explicit internship focus keywords to ensure strong segregation pool
        internship_kws = [
            ("software_engineering", "Software Engineering Intern"),
            ("it_tech_support", "IT Support Intern"),
            ("data_analytics", "Data Analyst Intern"),
            ("data_engineering", "Data Engineer Intern"),
            ("qa_testing", "QA Intern")
        ]
        for cat_key, kw in internship_kws:
            search_tasks.append((cat_key, kw, True))
            
        total_steps = len(self.scrapers) * len(search_tasks)
        current_step = 0

        for scraper in self.scrapers:
            for cat_key, kw, is_intern in search_tasks:
                current_step += 1
                msg = f"[{scraper.name}] Searching '{kw}' ({'Internship' if is_intern else 'Regular'})..."
                if progress_callback:
                    progress_callback(msg, current_step, total_steps)
                
                try:
                    items = scraper.scrape(kw, location=location, limit=limit_per_keyword)
                    for item in items:
                        # Ensure proper role category
                        if not item.role_category or item.role_category == "other":
                            item.role_category = cat_key
                        if is_intern:
                            item.job_type = "Internship"
                            
                        # Deduplicate
                        if item.id not in all_jobs:
                            all_jobs[item.id] = item
                except Exception as e:
                    logger.warning(f"Error scraping {scraper.name} with '{kw}': {e}")

        final_list = list(all_jobs.values())
        if progress_callback:
            progress_callback(f"Extraction completed! Total unique jobs gathered: {len(final_list)}", total_steps, total_steps)
            
        return final_list
