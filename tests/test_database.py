from pathlib import Path

from scraper_app.domain.models import ProjectConfig
from scraper_app.storage.database import Database


def test_project_jobs_records_and_deduplication(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    try:
        project_id = database.save_project(None, ProjectConfig("Shop", "https://example.test"))
        config = ProjectConfig("Shop", "https://example.test")
        job_id = database.create_job(project_id, config)
        record = {"url": "https://example.test/item/1", "title": "Item"}

        assert database.save_record(job_id, project_id, record, "url") is True
        assert database.save_record(job_id, project_id, record, "url") is False
        batch = [{"url": f"https://example.test/item/{index}"} for index in range(600)]
        assert database.save_records(job_id, project_id, batch, "url") == 599
        assert database.save_records(job_id, project_id, batch, "url") == 0
        assert database.project_records(project_id, limit=1) == [record]
        assert database.project_record_count(project_id) == 600
        assert len(list(database.iter_project_records(project_id))) == 600
        assert database.job_config(job_id) == config
        database.finish_job(job_id, "paused")
        assert database.resumable_job(project_id) == (job_id, 0)
        assert database.resume_job(job_id) == 0
        database.finish_job(job_id, "done")
        assert database.resumable_job(project_id) is None
        interrupted = database.create_job(project_id, config)
        assert database.resumable_job(project_id) == (interrupted, 0)
    finally:
        database.close()
