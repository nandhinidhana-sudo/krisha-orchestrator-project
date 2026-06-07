from pathlib import Path

from src.agents.orchestrator import Orchestrator
from src.config import AppConfig
from src.documents.pipeline import DocumentPipeline
from src.storage.database import Database


def make_app(tmp_path: Path):
    config = AppConfig(
        data_dir=tmp_path,
        upload_dir=tmp_path / "uploads",
        extracted_dir=tmp_path / "extracted",
        database_path=tmp_path / "app.db",
    )
    config.ensure_directories()
    db = Database(config.database_path)
    db.initialize()
    docs = DocumentPipeline(config, db)
    orchestrator = Orchestrator(config, db, docs)
    session_id = db.create_session("Test")
    return db, docs, orchestrator, session_id


def test_route_visual_request(tmp_path):
    _db, _docs, orchestrator, _session_id = make_app(tmp_path)

    plan = orchestrator.plan("Create a Mermaid diagram and Vega chart for the report")

    assert plan.needs_documents is True
    assert plan.needs_visualization is True
    assert "mermaid" in plan.visualization_types
    assert "vega_lite" in plan.visualization_types


def test_memory_compaction_marks_old_messages(tmp_path):
    db, _docs, orchestrator, session_id = make_app(tmp_path)
    for index in range(12):
        db.add_message(session_id, "user", f"Question {index}")

    result = orchestrator.compact_memory(session_id)

    assert "Compacted" in result
    assert db.latest_summary(session_id)


def test_orchestrator_creates_visual_artifacts(tmp_path):
    db, _docs, orchestrator, session_id = make_app(tmp_path)

    response = orchestrator.run(session_id, "Create a diagram and chart for this business process")
    artifacts = db.list_artifacts(session_id)

    assert "Artifacts" in response.answer
    assert {artifact["kind"] for artifact in artifacts} == {"mermaid", "vega_lite"}
