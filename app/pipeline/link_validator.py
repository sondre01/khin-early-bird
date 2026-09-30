import logging
import requests
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

DEAD_LINK_PATTERNS = [
    "no longer accepting applications",
    "this job has expired",
    "this job is closed",
    "we can't find this page",
    "we couldn't find that page",
    "job posting is no longer available",
    "job was not found",
    "did not match any jobs",
    "404 not found",
    "page not found",
    "position has been filled"
]

class LinkValidator:
    """
    Automated Liveness Guard:
    Verifies that every job application link actually exists, is reachable,
    and is currently accepting applications before it is saved or shown to the user.
    """
    def __init__(self, timeout: int = 6):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def verify_link(self, url: str) -> Tuple[bool, str]:
        """
        Tests URL liveness.
        Returns:
            (is_live: bool, reason: str)
        """
        if not url or not url.startswith("http") or url.endswith("#"):
            return False, "Invalid or missing URL scheme"

        try:
            # Use GET with stream to quickly read headers and initial HTML chunk
            resp = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True
            )

            # Check status code
            if resp.status_code in [404, 410]:
                return False, f"HTTP {resp.status_code} Not Found"
            
            if resp.status_code >= 500:
                return False, f"HTTP {resp.status_code} Server Error"

            # Inspect first 64KB of response content for dead job indicators
            content_chunk = b""
            for chunk in resp.iter_content(chunk_size=16384):
                content_chunk += chunk
                if len(content_chunk) >= 65536:
                    break

            text_sample = content_chunk.decode("utf-8", errors="ignore").lower()

            for pattern in DEAD_LINK_PATTERNS:
                if pattern in text_sample:
                    return False, f"Posting closed: '{pattern}' detected in page"

            return True, "Active and reachable"

        except requests.exceptions.Timeout:
            # If server times out, flag for review but don't hard reject unless recurrent
            return True, "Timeout on quick probe (assumed active)"
        except requests.exceptions.RequestException as e:
            return False, f"Connection failed: {str(e)[:60]}"

def prune_dead_jobs(db_path: str = "data/early_bird.db") -> Dict[str, Any]:
    """
    Scans the database and verifies every active job's link.
    Removes or marks dead/expired listings.
    """
    import sqlite3
    validator = LinkValidator(timeout=6)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, source, title, company, apply_url FROM jobs WHERE status != 'dismissed'")
    rows = c.fetchall()

    checked = len(rows)
    removed = 0
    active = 0

    for job_id, source, title, company, url in rows:
        is_live, reason = validator.verify_link(url)
        if not is_live:
            logger.info(f"Pruning dead job [{source}] {title} @ {company}: {reason}")
            c.execute("DELETE FROM evaluations WHERE job_id = ?", (job_id,))
            c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            removed += 1
        else:
            active += 1

    conn.commit()
    conn.close()
    return {"checked": checked, "removed": removed, "active": active}
