from engine.project.manager import ProjectManager
from engine.project.manifest import ProductionManifest, Shot
from engine.project.database import JobDB


def test_project_crud_and_resume(workdir):
    pm = ProjectManager("outputs")
    m = ProductionManifest(job_id="job1", topic="test topic")
    m.shots = [Shot(shot_id="shot_001", status="accepted"), Shot(shot_id="shot_002")]
    pm.create(m)
    assert (pm.job_dir("job1") + "/production_manifest.json")
    m2 = pm.load_manifest("job1")
    assert len(m2.shots) == 2 and m2.accepted_count() == 1
    assert [s.shot_id for s in m2.pending_shots()] == ["shot_002"]
    # resume: update second shot, reload
    s = m2.shots[1]
    s.status = "accepted"
    pm.update_shot("job1", s)
    assert pm.load_manifest("job1").accepted_count() == 2
    assert "job1" in pm.list_jobs()


def test_jobdb(workdir):
    db = JobDB("data/jobs.db")
    db.upsert("job1", topic="t", status="planned", est_credits=50)
    db.bump("job1", "accepted_shots")
    r = db.get("job1")
    assert r["status"] == "planned" and r["accepted_shots"] == 1 and r["est_credits"] == 50
    assert db.list()[0]["job_id"] == "job1"
