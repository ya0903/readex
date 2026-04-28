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

    # APScheduler weekday names, indexed 0=Mon..6=Sun (matches Python's weekday()).
    _DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

    def add_job(
        self,
        series_id: int,
        interval_seconds: int,
        check_time: str | None = None,
        check_day_of_week: int | None = None,
    ):
        """Schedule a recurring check for a series.

        If `check_time` ("HH:MM") is set and the interval is Daily/Weekly,
        uses a CronTrigger so the check fires at that specific time. For
        Weekly, `check_day_of_week` (0=Mon..6=Sun) picks the day; defaults
        to Monday if unset.
        """
        job_id = f"series_{series_id}"
        trigger = self._make_trigger(interval_seconds, check_time, check_day_of_week)
        self._scheduler.add_job(
            self._check_func,
            trigger=trigger,
            id=job_id, args=[series_id], replace_existing=True,
        )

    def _make_trigger(
        self,
        interval_seconds: int,
        check_time: str | None,
        check_day_of_week: int | None = None,
    ):
        if check_time and interval_seconds >= 86400:
            hour, minute = self._parse_time(check_time)
            if interval_seconds >= 604800:
                # Weekly — fire once a week at the given time on the chosen day
                dow_idx = check_day_of_week if check_day_of_week is not None else 0
                dow_idx = max(0, min(6, int(dow_idx)))
                return CronTrigger(
                    day_of_week=self._DOW_NAMES[dow_idx],
                    hour=hour, minute=minute,
                )
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

    def update_job(
        self,
        series_id: int,
        interval_seconds: int,
        check_time: str | None = None,
        check_day_of_week: int | None = None,
    ):
        self.add_job(series_id, interval_seconds, check_time, check_day_of_week)

    def get_job(self, series_id: int):
        job_id = f"series_{series_id}"
        return self._scheduler.get_job(job_id)

    def list_jobs(self):
        return self._scheduler.get_jobs()
