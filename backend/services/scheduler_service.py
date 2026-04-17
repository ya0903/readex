# readex/backend/services/scheduler_service.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


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

    def add_job(self, series_id: int, interval_seconds: int, check_time: str | None = None):
        """Schedule a recurring check for a series.

        If `check_time` is set (as "HH:MM") and the interval is Daily (86400)
        or Weekly (604800), uses a CronTrigger so the check fires at that
        specific time of day. Otherwise falls back to an IntervalTrigger.
        """
        job_id = f"series_{series_id}"
        trigger = self._make_trigger(interval_seconds, check_time)
        self._scheduler.add_job(
            self._check_func,
            trigger=trigger,
            id=job_id, args=[series_id], replace_existing=True,
        )

    def _make_trigger(self, interval_seconds: int, check_time: str | None):
        if check_time and interval_seconds >= 86400:
            hour, minute = self._parse_time(check_time)
            if interval_seconds >= 604800:
                # Weekly — fire once a week at the given time (Monday)
                return CronTrigger(day_of_week="mon", hour=hour, minute=minute)
            else:
                # Daily — fire once a day at the given time
                return CronTrigger(hour=hour, minute=minute)
        return IntervalTrigger(seconds=interval_seconds)

    @staticmethod
    def _parse_time(check_time: str) -> tuple[int, int]:
        """Parse "HH:MM" into (hour, minute). Falls back to (0, 0)."""
        try:
            parts = check_time.strip().split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 0, 0

    def remove_job(self, series_id: int):
        job_id = f"series_{series_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def update_job(self, series_id: int, interval_seconds: int, check_time: str | None = None):
        self.add_job(series_id, interval_seconds, check_time)

    def get_job(self, series_id: int):
        job_id = f"series_{series_id}"
        return self._scheduler.get_job(job_id)

    def list_jobs(self):
        return self._scheduler.get_jobs()
