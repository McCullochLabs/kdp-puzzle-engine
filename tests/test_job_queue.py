from publishing.job_queue import ProductionJobQueue
from datetime import datetime, timedelta

def test_queue_allows_one_heavy_job_and_releases(tmp_path):
    queue=ProductionJobQueue(tmp_path)
    assert queue.acquire("one", "First book")[0]
    assert not queue.acquire("two", "Second book")[0]
    queue.release("one", "complete")
    assert queue.acquire("two", "Second book")[0]


def test_queue_recovers_a_stale_interrupted_build(tmp_path):
    queue = ProductionJobQueue(tmp_path)
    assert queue.acquire("old", "Interrupted book")[0]
    state = queue.status()
    state["active"]["started"] = (datetime.now() - timedelta(hours=7)).isoformat(timespec="seconds")
    queue._save(state)
    assert queue.acquire("new", "New book")[0]
    assert queue.status()["active"]["job_id"] == "new"
