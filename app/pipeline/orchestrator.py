import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional
from app.scrapers.aggregator import JobAggregator
from app.pipeline.normalizer import JobNormalizer
from app.pipeline.ai_matcher import AIJobMatcher
from app.pipeline.notifier import EmailNotifier
from app.pipeline.link_validator import LinkValidator
from app.database import (
    start_scrape_run, finish_scrape_run, save_job, save_evaluation, get_jobs
)
from app.config import USER_EMAIL, DEFAULT_TARGET_LOCATION, FILTER_NCR_ONLY
from app.utils.location import is_ncr_location

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.aggregator = JobAggregator()
        self.normalizer = JobNormalizer()
        self.ai_matcher = AIJobMatcher(api_key=gemini_api_key)
        self.notifier = EmailNotifier()
        self.link_validator = LinkValidator(timeout=6)

    def run(
        self,
        location: str = DEFAULT_TARGET_LOCATION,
        limit_per_keyword: int = 4,
        send_email: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the 4-phase pipeline:
        Phase 1: Extraction (LinkedIn, Jobstreet, Indeed)
        Phase 2: Normalization & Deduplication
        Phase 3: AI Validation & Profile Matching (Gemini)
        Phase 4: Notification & Delivery (Email Digest)
        """
        run_id = start_scrape_run()
        log_records = []

        def emit(phase_id: int, phase_name: str, message: str, percent: int):
            ts = datetime.now().strftime("%H:%M:%S")
            log_line = f"[{ts}] [{phase_name}] {message}"
            log_records.append(log_line)
            logger.info(log_line)
            if progress_callback:
                progress_callback({
                    "phase_id": phase_id,
                    "phase_name": phase_name,
                    "message": message,
                    "percent": percent,
                    "timestamp": ts
                })

        try:
            # ==========================================
            # PHASE 1: EXTRACTION
            # ==========================================
            emit(1, "Extraction", "Starting multi-source ingestion across LinkedIn, Jobstreet, Indeed...", 5)
            
            def scraper_cb(msg, cur, tot):
                pct = 5 + int((cur / max(1, tot)) * 30)
                emit(1, "Extraction", msg, pct)

            raw_jobs = self.aggregator.run_all(
                location=location,
                limit_per_keyword=limit_per_keyword,
                progress_callback=scraper_cb
            )
            emit(1, "Extraction", f"Completed extraction! Gathered {len(raw_jobs)} unique listings.", 35)

            # ==========================================
            # PHASE 2: NORMALIZATION, LINK VERIFICATION & DEDUPLICATION
            # ==========================================
            emit(2, "Transformation", "Verifying live application links, cleaning, and standardizing schemas...", 40)
            normalized_jobs = []
            new_jobs_count = 0
            dead_links_rejected = 0
            experience_rejected = 0

            for i, raw_item in enumerate(raw_jobs):
                cleaned = self.normalizer.normalize(raw_item)
                
                # Automated Liveness Guard: Verify URL actually accepts applications
                apply_url = cleaned.get("apply_url", "")
                is_live, reason = self.link_validator.verify_link(apply_url)
                if not is_live:
                    dead_links_rejected += 1
                    logger.warning(f"Discarded non-live posting: {cleaned['title']} @ {cleaned['company']} ({reason})")
                    continue

                # Recency Guard: Filter out roles posted a month ago or older (e.g. 1 month ago, 6 months ago, 4 weeks ago)
                p_date = (cleaned.get("posted_date") or "").lower()
                if any(w in p_date for w in ["month", "year", "4 week", "4 weeks"]) or re.search(r'([3-9]|\d{2,})\s*week', p_date):
                    logger.info(f"Discarded stale posting ({cleaned.get('posted_date')}): {cleaned['title']} @ {cleaned['company']}")
                    continue

                # Experience & Seniority Guard: Discard roles demanding seniority or prior full-time experience for Regular jobs
                if cleaned.get("job_type") == "Regular" and not cleaned.get("is_fresh_grad_acceptable", True):
                    experience_rejected += 1
                    logger.info(f"Discarded non-fresh-graduate posting ({cleaned.get('fresh_grad_reason')}): {cleaned['title']} @ {cleaned['company']}")
                    continue

                # Location Guard: Ensure opportunities are in NCR / Metro Manila or Remote
                if FILTER_NCR_ONLY and not is_ncr_location(cleaned.get("location"), cleaned.get("work_type")):
                    logger.info(f"Discarded non-NCR posting ({cleaned.get('location')}): {cleaned['title']} @ {cleaned['company']}")
                    continue

                is_new = save_job(cleaned)
                if is_new:
                    new_jobs_count += 1
                normalized_jobs.append(cleaned)
                
            emit(2, "Transformation", f"Transformation complete. {len(normalized_jobs)} live jobs verified ({dead_links_rejected} dead links rejected, {experience_rejected} senior/ineligible roles filtered, {new_jobs_count} new entries saved).", 55)

            # ==========================================
            # PHASE 3: AI VALIDATION & MATCHING
            # ==========================================
            emit(3, "AI Validation", "Executing qualification matching and scoring with Gemini AI / Profile Engine...", 60)
            high_match_count = 0
            evaluated_jobs = []

            total_jobs = len(normalized_jobs)
            for idx, job in enumerate(normalized_jobs):
                evaluation = self.ai_matcher.evaluate_job(job)
                save_evaluation(evaluation)
                
                # Combine job dict with evaluation
                combined = {**job, **evaluation}
                evaluated_jobs.append(combined)
                
                if evaluation.get("match_score", 0) >= 80:
                    high_match_count += 1
                    
                pct = 60 + int(((idx + 1) / max(1, total_jobs)) * 25)
                if (idx + 1) % 5 == 0 or (idx + 1) == total_jobs:
                    emit(3, "AI Validation", f"Evaluated {idx + 1}/{total_jobs} postings... ({high_match_count} high matches found)", pct)

            emit(3, "AI Validation", f"AI Validation finished! {high_match_count} roles scored >= 80% match.", 85)

            # ==========================================
            # PHASE 4: NOTIFICATION & DELIVERY
            # ==========================================
            emit(4, "Delivery", "Generating responsive HTML digest and dispatching notification...", 90)
            
            # Fetch top jobs to include in digest (excluding already applied or cancelled/dismissed jobs)
            existing_statuses = {j["id"]: j.get("status", "new") for j in get_jobs(status="all", location_filter="all")}
            active_evaluated = [
                j for j in evaluated_jobs
                if existing_statuses.get(j.get("id"), "new") not in ("applied", "dismissed")
            ]
            top_jobs = [j for j in active_evaluated if j.get("match_score", 0) >= 60]
            if not top_jobs:
                top_jobs = active_evaluated[:10]
                
            email_sent = False
            if send_email:
                email_sent = self.notifier.send_digest(top_jobs, recipient=USER_EMAIL)
                if email_sent:
                    emit(4, "Delivery", f"Email digest sent to {USER_EMAIL}!", 98)
                else:
                    emit(4, "Delivery", "Generated local HTML digest snapshot at data/latest_digest.html (SMTP credentials pending).", 98)

            emit(4, "Delivery", "Pipeline run finished successfully!", 100)

            full_log = "\n".join(log_records)
            finish_scrape_run(
                run_id=run_id,
                total_scraped=len(raw_jobs),
                total_new=new_jobs_count,
                total_high_match=high_match_count,
                status="completed",
                log=full_log
            )

            return {
                "success": True,
                "run_id": run_id,
                "total_scraped": len(raw_jobs),
                "total_new": new_jobs_count,
                "high_match_count": high_match_count,
                "email_sent": email_sent,
                "log": log_records
            }

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            err_msg = f"Fatal pipeline error: {str(e)}"
            emit(0, "Error", err_msg, 100)
            finish_scrape_run(
                run_id=run_id,
                total_scraped=0,
                total_new=0,
                total_high_match=0,
                status="failed",
                log="\n".join(log_records) + f"\n{err_msg}"
            )
            return {
                "success": False,
                "run_id": run_id,
                "error": str(e),
                "log": log_records
            }
