"""SQLite persistence for projects, jobs, checkpoints, and scraped records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from scraper_app.domain.models import ProjectConfig


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    jobs: Mapped[list[JobRow]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    checkpoint: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[ProjectRow] = relationship(back_populates="jobs")
    records: Mapped[list[RecordRow]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class RecordRow(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("project_id", "record_key", name="uq_record_project_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    job: Mapped[JobRow] = relationship(back_populates="records")


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(connection: Any, _: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.exec_driver_sql("PRAGMA synchronous=NORMAL")
            connection.commit()
        Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def list_projects(self) -> list[tuple[int, ProjectConfig]]:
        with self._sessions() as session:
            rows = session.scalars(select(ProjectRow).order_by(ProjectRow.updated_at.desc())).all()
            return [(row.id, ProjectConfig.from_dict(json.loads(row.config_json))) for row in rows]

    def save_project(self, project_id: int | None, config: ProjectConfig) -> int:
        with self._sessions.begin() as session:
            row = session.get(ProjectRow, project_id) if project_id is not None else None
            if row is None:
                row = ProjectRow(name=config.name, config_json="")
                session.add(row)
            row.name = config.name
            row.config_json = json.dumps(config.to_dict(), ensure_ascii=False)
            session.flush()
            return row.id

    def create_job(self, project_id: int, config: ProjectConfig) -> int:
        with self._sessions.begin() as session:
            job = JobRow(
                project_id=project_id,
                config_json=json.dumps(config.to_dict(), ensure_ascii=False),
                status="running",
            )
            session.add(job)
            session.flush()
            return job.id

    def resumable_job(self, project_id: int) -> tuple[int, int] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(JobRow)
                .where(
                    JobRow.project_id == project_id,
                    JobRow.status.in_(("paused", "failed", "running")),
                )
                .order_by(JobRow.started_at.desc())
                .limit(1)
            )
            return (row.id, row.checkpoint) if row is not None else None

    def resume_job(self, job_id: int) -> int:
        with self._sessions.begin() as session:
            job = session.get(JobRow, job_id)
            if job is None:
                raise ValueError(f"Job {job_id} tidak ditemukan.")
            job.status = "running"
            job.error = ""
            return job.checkpoint

    def job_config(self, job_id: int) -> ProjectConfig:
        with self._sessions() as session:
            job = session.get(JobRow, job_id)
            if job is None:
                raise ValueError(f"Job {job_id} tidak ditemukan.")
            return ProjectConfig.from_dict(json.loads(job.config_json))

    def set_job_status(self, job_id: int, status: str) -> None:
        with self._sessions.begin() as session:
            job = session.get(JobRow, job_id)
            if job is not None:
                job.status = status

    def save_record(
        self, job_id: int, project_id: int, data: dict[str, Any], unique_field: str
    ) -> bool:
        return self.save_records(job_id, project_id, [data], unique_field) == 1

    def save_records(
        self,
        job_id: int,
        project_id: int,
        records: list[dict[str, Any]],
        unique_field: str,
    ) -> int:
        if not records:
            return 0
        values = []
        for data in records:
            raw_key = str(data.get(unique_field, "")) if unique_field else ""
            if not raw_key:
                raw_key = json.dumps(data, sort_keys=True, ensure_ascii=False)
            values.append(
                {
                    "job_id": job_id,
                    "project_id": project_id,
                    "record_key": hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
                    "data_json": json.dumps(data, ensure_ascii=False),
                }
            )
        with self._sessions.begin() as session:
            inserted = 0
            for start in range(0, len(values), 250):
                statement = (
                    sqlite_insert(RecordRow)
                    .values(values[start : start + 250])
                    .on_conflict_do_nothing(index_elements=["project_id", "record_key"])
                )
                result = session.execute(statement)
                inserted += max(result.rowcount or 0, 0)
            return inserted

    def update_checkpoint(self, job_id: int, page: int) -> None:
        with self._sessions.begin() as session:
            job = session.get(JobRow, job_id)
            if job is not None:
                job.checkpoint = page

    def finish_job(self, job_id: int, status: str, error: str = "") -> None:
        with self._sessions.begin() as session:
            job = session.get(JobRow, job_id)
            if job is not None:
                job.status = status
                job.error = error
                job.finished_at = datetime.now(UTC)

    def project_records(
        self, project_id: int, limit: int | None = None, newest: bool = False
    ) -> list[dict[str, Any]]:
        with self._sessions() as session:
            ordering = RecordRow.id.desc() if newest else RecordRow.id
            stmt = (
                select(RecordRow.data_json)
                .where(RecordRow.project_id == project_id)
                .order_by(ordering)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            records = [json.loads(value) for value in session.scalars(stmt)]
            return list(reversed(records)) if newest else records

    def iter_project_records(self, project_id: int) -> Iterator[dict[str, Any]]:
        with self._sessions() as session:
            stmt = (
                select(RecordRow.data_json)
                .where(RecordRow.project_id == project_id)
                .order_by(RecordRow.id)
                .execution_options(yield_per=500)
            )
            for value in session.scalars(stmt):
                yield json.loads(value)

    def project_record_count(self, project_id: int) -> int:
        with self._sessions() as session:
            return int(
                session.scalar(
                    select(func.count(RecordRow.id)).where(RecordRow.project_id == project_id)
                )
                or 0
            )

    def close(self) -> None:
        self.engine.dispose()
