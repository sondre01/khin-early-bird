import re
import urllib.parse
from typing import Optional, Dict

def resolve_apply_url(source: str, title: str, company: str, raw_url: Optional[str] = None) -> str:
    """
    Sanitizes and resolves job application URLs to prevent 404s ('We can't find this page').
    - If a URL contains a direct verified ID (e.g. LinkedIn numeric ID, Indeed 16-hex JK, Jobstreet numeric ID),
      cleans tracking parameters and returns it.
    - If a URL contains a non-existent slug or placeholder (e.g. Indeed jk=slug, Jobstreet /job/slug),
      automatically transforms it into the platform's direct live search query which NEVER 404s.
    - If missing or empty, generates a targeted Google Jobs / search application URL.
    """
    source_lower = (source or "").strip().lower()
    raw = (raw_url or "").strip()
    
    clean_company = re.sub(r'[\(\)\[\]\{\}]', '', company or '').strip()
    clean_title = re.sub(r'[\(\)\[\]\{\}]', '', title or '').strip()
    search_query = f"{clean_company} {clean_title}".strip()
    encoded_q = urllib.parse.quote_plus(search_query)

    # 1. Indeed resolution
    if "indeed" in source_lower or "indeed.com" in raw:
        # Indeed valid Job Keys are exactly 16 hex characters [0-9a-fA-F]{16}
        jk_match = re.search(r"[?&]jk=([a-fA-F0-9]{16})\b", raw)
        if jk_match:
            return f"https://ph.indeed.com/viewjob?jk={jk_match.group(1)}"
        # If it's a slug, invalid jk, or generic link, route to live search on Indeed PH
        return f"https://ph.indeed.com/jobs?q={encoded_q}&l=Philippines"

    # 2. Jobstreet / SEEK resolution
    elif "jobstreet" in source_lower or "jobstreet.com" in raw:
        # Jobstreet / SEEK direct job IDs are digits: /job/12345678 or /jobs/12345678
        job_id_match = re.search(r"/job(?:s)?/(\d{6,12})\b", raw)
        if job_id_match:
            return f"https://ph.jobstreet.com/job/{job_id_match.group(1)}"
        # If it's a slug or generic link, route to live search on Jobstreet PH
        return f"https://ph.jobstreet.com/jobs?keywords={encoded_q}"

    # 3. LinkedIn resolution
    elif "linkedin" in source_lower or "linkedin.com" in raw:
        # Check for numeric job ID in LinkedIn URLs (e.g. /jobs/view/...-1234567890)
        view_match = re.search(r"/jobs/view/(?:[a-zA-Z0-9\-]+-)?(\d{8,14})\b", raw)
        if view_match:
            return f"https://ph.linkedin.com/jobs/view/{view_match.group(1)}"
        if "linkedin.com/jobs/view" in raw:
            # Strip query params like ?refId=...&trackingId=...
            return raw.split("?")[0]
        # Generic or search link fallback
        return f"https://www.linkedin.com/jobs/search/?keywords={encoded_q}&location=Philippines"

    # 4. Direct / Unknown source
    if raw and raw.startswith("http") and not raw.endswith("#"):
        return raw

    # Fallback to Google Jobs
    return f"https://www.google.com/search?q={encoded_q}+apply+Philippines"

def get_job_link_alternatives(source: str, title: str, company: str, apply_url: Optional[str] = None) -> Dict[str, str]:
    """
    Returns a dictionary of resilient application and search URLs for any job.
    Includes primary apply link, Google Jobs search, LinkedIn search, and Company Careers search.
    """
    primary = resolve_apply_url(source, title, company, apply_url)
    clean_company = re.sub(r'[\(\)\[\]\{\}]', '', company or '').strip()
    clean_title = re.sub(r'[\(\)\[\]\{\}]', '', title or '').strip()
    search_q = urllib.parse.quote_plus(f"{clean_company} {clean_title}")
    company_q = urllib.parse.quote_plus(clean_company)

    return {
        "primary": primary,
        "google_jobs": f"https://www.google.com/search?q={search_q}+apply+Philippines",
        "linkedin": f"https://www.linkedin.com/jobs/search/?keywords={search_q}&location=Philippines",
        "company_careers": f"https://www.google.com/search?q={company_q}+careers+Philippines"
    }
