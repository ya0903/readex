# readex/backend/services/scheduler_service.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.interval import IntervalTrigger


def _noop_check(series_id: int):
    """Placeholder — replaced at app startup with actual update check logic."""
    pass


class SchedulerService:
    def __init__(self, check_func=None):
        self._check_func = check_func or _noop_check
        self._scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
        )

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start(paused=False)

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def add_job(self, series_id: int, interval_seconds: int):
        job_id = f"series_{series_id}"
        self._scheduler.add_job(
            self._check_func,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id, args=[series_id], replace_existing=True,
        )

    def remove_job(self, series_id: int):
        job_id = f"series_{series_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def update_job(self, series_id: int, interval_seconds: int):
        self.add_job(series_id, interval_seconds)

    def get_job(self, series_id: int):
        job_id = f"series_{series_id}"
        return self._scheduler.get_job(job_id)

    def list_jobs(self):
        return self._scheduler.get_jobs()
