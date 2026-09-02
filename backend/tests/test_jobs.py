from app.jobs import create_job, get_job, set_failed, set_result, set_status


def test_create_job_starts_in_separating_status():
    job_id = create_job()
    job = get_job(job_id)
    assert job.status == "separating"
    assert job.result is None
    assert job.detail is None


def test_set_status_updates_an_existing_job():
    job_id = create_job()
    set_status(job_id, "arranging")
    assert get_job(job_id).status == "arranging"


def test_set_result_marks_job_done_with_result_payload():
    job_id = create_job()
    set_result(job_id, {"song_id": "abc", "title": "Song", "difficulties": {}})
    job = get_job(job_id)
    assert job.status == "done"
    assert job.result == {"song_id": "abc", "title": "Song", "difficulties": {}}


def test_set_failed_marks_job_failed_with_detail():
    job_id = create_job()
    set_failed(job_id, "boom")
    job = get_job(job_id)
    assert job.status == "failed"
    assert job.detail == "boom"


def test_get_job_returns_none_for_unknown_id():
    assert get_job("does-not-exist") is None
