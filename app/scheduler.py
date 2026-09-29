import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import DAILY_RUN_TIME
from app.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

class EarlyBirdScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.orchestrator = PipelineOrchestrator()
        self.job_id = "daily_job_hunt"
        self._is_running = False

    def start(self, run_time_str: str = DAILY_RUN_TIME):
        """Starts the daily automated job scraper at run_time_str (format 'HH:MM')"""
        if self._is_running:
            return

        try:
            hour, minute = map(int, run_time_str.split(":"))
        except Exception:
            hour, minute = 8, 0

        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self._scheduled_task,
            trigger=trigger,
            id=self.job_id,
            name="Daily Job Extraction & Matching",
            replace_existing=True
        )
        self.scheduler.start()
        self._is_running = True
        logger.info(f"Scheduler started. Daily run set for {hour:02d}:{minute:02d} local time.")

    def stop(self):
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler stopped.")

    def update_schedule(self, run_time_str: str):
        """Updates the daily execution time"""
        try:
            hour, minute = map(int, run_time_str.split(":"))
            trigger = CronTrigger(hour=hour, minute=minute)
            self.scheduler.reschedule_job(self.job_id, trigger=trigger)
            logger.info(f"Rescheduled daily run to {hour:02d}:{minute:02d}")
            return True
        except Exception as e:
            logger.error(f"Failed to reschedule: {e}")
            return False

    def get_status(self):
        job = self.scheduler.get_job(self.job_id) if self._is_running else None
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
        return {
            "is_active": self._is_running,
            "next_run": next_run
        }

    def _scheduled_task(self):
        logger.info("Triggering scheduled automated daily job run...")
        try:
            res = self.orchestrator.run(send_email=True)
            logger.info(f"Scheduled run completed. Result: {res.get('success')}")
        except Exception as e:
            logger.error(f"Error in scheduled task: {e}")

scheduler_instance = EarlyBirdScheduler()
