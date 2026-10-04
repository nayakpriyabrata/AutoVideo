from types import SimpleNamespace

from engine.factory import Factory


def test_unresolved_flow_failure_log_keeps_provider_cause_without_resubmitting():
    shot = SimpleNamespace(shot_id="shot_001", accepted_take=None, status="generating")
    manifest = SimpleNamespace(job_id="job-123", status="generating", shots=[shot])
    events = []

    class ProjectManager:
        def load_manifest(self, _job_id):
            return manifest

        def save_manifest(self, _manifest):
            return None

        def log(self, _job_id, event, data):
            events.append((event, data))

    class Database:
        def upsert(self, *_args, **_kwargs):
            return None

    factory = Factory.__new__(Factory)
    factory.pm = ProjectManager()
    factory.db = Database()

    factory._fail_pending_flow(
        manifest,
        "shot_001",
        RuntimeError("download validation failed after exact video tile lookup"),
        "https://flow.google.com/project/saved-project",
    )

    assert manifest.status == "failed"
    assert shot.status == "failed"
    assert events[0][0] == "flow_request_failed_without_pause"
    assert "exact video tile lookup" in events[0][1]["error"]
    assert events[0][1]["error_type"] == "RuntimeError"
