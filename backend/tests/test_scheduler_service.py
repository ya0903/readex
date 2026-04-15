# readex/backend/tests/test_scheduler_service.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Series, Schedule
from services.scheduler_service import SchedulerService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def service():
    svc = SchedulerService()
    svc.start()
    yield svc
    svc.stop()


_series_counter = 0


def _make_series_with_schedule(db, interval=21600, enabled=True):
    global _series_counter
    _series_counter += 1
    series = Series(
        title=f"Test {_series_counter}", folder_name=f"Test {_series_counter}",
        source_name="mangadex", source_id=f"x{_series_counter}",
        content_type="manga", status="ongoing",
    )
    db.add(series)
    db.commit()
    schedule = Schedule(
        series_id=series.id, interval_seconds=interval, enabled=enabled,
    )
    db.add(schedule)
    db.commit()
    return series, schedule


def test_add_job(service, db):
    series, schedule = _make_series_with_schedule(db)
    service.add_job(series.id, schedule.interval_seconds)
    job = service.get_job(series.id)
    assert job is not None


def test_remove_job(service, db):
    series, schedule = _make_series_with_schedule(db)
    service.add_job(series.id, schedule.interval_seconds)
    service.remove_job(series.id)
    job = service.get_job(series.id)
    assert job is None


def test_update_job_interval(service, db):
    series, schedule = _make_series_with_schedule(db)
    service.add_job(series.id, 3600)
    service.update_job(series.id, 7200)
    job = service.get_job(series.id)
    assert job is not None


def test_list_jobs(service, db):
    s1, _ = _make_series_with_schedule(db)
    s2, _ = _make_series_with_schedule(db)
    service.add_job(s1.id, 3600)
    service.add_job(s2.id, 7200)
    jobs = service.list_jobs()
    assert len(jobs) == 2
