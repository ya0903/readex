from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    folder_name: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)  # manga, manhwa, comic
    status: Mapped[str] = mapped_column(String, nullable=False)  # ongoing, complete
    metadata_url: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("source_name", "source_id"),)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="series", cascade="all, delete-orphan")
    schedule: Mapped["Schedule | None"] = relationship(back_populates="series", uselist=False, cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id"), nullable=False)
    chapter_number: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    source_chapter_id: Mapped[str] = mapped_column(String, nullable=False)
    source_chapter_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # available, queued, downloading, downloaded, failed
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("series_id", "source_chapter_id"),)

    series: Mapped["Series"] = relationship(back_populates="chapters")
    queue_entry: Mapped["DownloadQueue | None"] = relationship(
        back_populates="chapter", uselist=False, cascade="all, delete-orphan"
    )


class DownloadQueue(Base):
    __tablename__ = "download_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(Integer, ForeignKey("chapters.id"), nullable=False, unique=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chapter: Mapped["Chapter"] = relationship(back_populates="queue_entry")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id"), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    series: Mapped["Series"] = relationship(back_populates="schedule")
