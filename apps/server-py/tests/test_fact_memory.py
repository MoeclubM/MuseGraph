from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import fact_memory
from app.services.fact_memory import FACT_SYNC_TASK_TYPE, schedule_fact_memory_sync
from app.services.task_state import task_manager


def test_fact_sync_requires_all_component_models():
    project = SimpleNamespace(
        component_models={
            "ontology_generation": "model-ontology",
            "operation_agent_task": "model-agent",
            "memory_build": "model-memory",
        }
    )

    with pytest.raises(RuntimeError, match="memory_embedding"):
        fact_memory._require_fact_sync_models(project)


def test_schedule_fact_memory_sync_creates_task(monkeypatch):
    task_manager.cleanup_old_tasks(max_age_hours=0)

    class _DummyRunner:
        def done(self):
            return False

    def _create_task(coro):
        coro.close()
        return _DummyRunner()

    monkeypatch.setattr("app.services.fact_memory.asyncio.create_task", _create_task)

    task_id = schedule_fact_memory_sync(
        project_id="proj-1",
        user_id="user-1",
        action="create",
        fact_id="fact-1",
    )
    task = task_manager.get_task(task_id)

    assert task is not None
    assert task.task_type == FACT_SYNC_TASK_TYPE
    assert task.metadata["project_id"] == "proj-1"
    assert task.metadata["fact_id"] == "fact-1"
    assert task.metadata["action"] == "create"
    assert task.metadata["auto_created"] is True
    task_manager.unregister_runner(task_id)
