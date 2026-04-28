from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import Schedule, Series
from schemas import ScheduleCreate, ScheduleUpdate, ScheduleOut

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _scheduler(request: Request):
    return getattr(request.app.state, "scheduler", None)


@router.get("", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db)):
    return db.query(Schedule).order_by(Schedule.next_check_at).all()


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(
    data: ScheduleCreate, request: Request, db: Session = Depends(get_db)
):
    series = db.get(Series, data.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    # Upsert: replace any existing schedule for this series.
    existing = db.query(Schedule).filter_by(series_id=data.series_id).first()
    if existing:
        existing.interval_seconds = data.interval_seconds
        existing.check_time = data.check_time
        existing.check_day_of_week = data.check_day_of_week
        existing.enabled = data.enabled
        db.commit()
        db.refresh(existing)
        sched = existing
    else:
        sched = Schedule(
            series_id=data.series_id, interval_seconds=data.interval_seconds,
            check_time=data.check_time, check_day_of_week=data.check_day_of_week,
            enabled=data.enabled,
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)

    sc = _scheduler(request)
    if sc:
        if sched.enabled:
            sc.add_job(
                sched.series_id, sched.interval_seconds,
                sched.check_time, sched.check_day_of_week,
            )
        else:
            sc.remove_job(sched.series_id)

    # Set next_check_at so the dashboard countdown is accurate.
    from datetime import datetime, timedelta
    sched.next_check_at = datetime.utcnow() + timedelta(seconds=sched.interval_seconds)
    db.commit()
    db.refresh(sched)
    return sched


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int, data: ScheduleUpdate, request: Request, db: Session = Depends(get_db)
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)

    sc = _scheduler(request)
    if sc:
        if schedule.enabled:
            sc.add_job(
                schedule.series_id, schedule.interval_seconds,
                schedule.check_time, schedule.check_day_of_week,
            )
        else:
            sc.remove_job(schedule.series_id)
    return schedule


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: int, request: Request, db: Session = Depends(get_db)
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    series_id = schedule.series_id
    db.delete(schedule)
    db.commit()
    sc = _scheduler(request)
    if sc:
        sc.remove_job(series_id)
