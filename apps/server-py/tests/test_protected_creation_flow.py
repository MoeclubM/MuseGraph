import asyncio
import os
import secrets

import httpx
import pytest


pytestmark = pytest.mark.protected


def csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["musegraph_csrf"]}


@pytest.mark.asyncio
async def test_real_provider_creation_uses_structured_knowledge_and_publishes_one_revision():
    base_url = os.environ.get("MUSEGRAPH_TEST_BASE_URL")
    admin_email = os.environ.get("SEED_ADMIN_EMAIL")
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD")
    provider_api_key = os.environ.get("MUSEGRAPH_PROVIDER_API_KEY")
    provider_base_url = os.environ.get("MUSEGRAPH_PROVIDER_BASE_URL")
    model = os.environ.get("MUSEGRAPH_PROVIDER_MODEL")
    embedding_model = os.environ.get("MUSEGRAPH_EMBEDDING_MODEL")
    embedding_dimensions = os.environ.get("MUSEGRAPH_EMBEDDING_DIMENSIONS")
    assert base_url, "MUSEGRAPH_TEST_BASE_URL is required"
    assert admin_email and admin_password, "Seed administrator credentials are required"
    assert provider_api_key, "MUSEGRAPH_PROVIDER_API_KEY is required"
    assert model, "MUSEGRAPH_PROVIDER_MODEL is required"
    assert embedding_model, "MUSEGRAPH_EMBEDDING_MODEL is required"
    assert embedding_dimensions and embedding_dimensions.isdigit()

    timeout = httpx.Timeout(1200)
    async with (
        httpx.AsyncClient(base_url=base_url, timeout=timeout) as admin,
        httpx.AsyncClient(base_url=base_url, timeout=timeout) as user,
    ):
        login = await admin.post(
            "/api/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        assert login.status_code == 200, login.text
        provider = await admin.post(
            "/api/admin/providers",
            headers=csrf_headers(admin),
            json={
                "name": f"Protected provider {secrets.token_hex(4)}",
                "provider": "openai_compatible",
                "api_key": provider_api_key,
                "base_url": provider_base_url or None,
                "is_active": True,
                "priority": 1000,
            },
        )
        assert provider.status_code == 200, provider.text
        provider_id = provider.json()["id"]
        chat_binding = await admin.post(
            f"/api/admin/providers/{provider_id}/models",
            headers=csrf_headers(admin),
            json={"model": model},
        )
        assert chat_binding.status_code == 200, chat_binding.text
        embedding_binding = await admin.post(
            f"/api/admin/providers/{provider_id}/embedding-models",
            headers=csrf_headers(admin),
            json={"model": embedding_model},
        )
        assert embedding_binding.status_code == 200, embedding_binding.text

        registration = await user.post(
            "/api/auth/register",
            json={
                "email": f"protected-{secrets.token_hex(6)}@example.com",
                "password": "Protected-Creation-Password-2026!",
                "nickname": "Protected Creation",
            },
        )
        assert registration.status_code == 201, registration.text
        project_response = await user.post(
            "/api/projects",
            headers=csrf_headers(user),
            json={
                "title": "Structured knowledge creation proof",
                "pack_slug": "novel",
                "component_models": {
                    "operation_agent_task": model,
                    "operation_analyze": model,
                    "operation_agent_suggest": model,
                    "memory_llm": model,
                    "memory_embedding": embedding_model,
                    "memory_embedding_dimensions": embedding_dimensions,
                },
            },
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        project_id = project["id"]
        base_revision_id = project["active_revision_id"]

        records = [
            {
                "operation": "upsert",
                "record": {
                    "kind": "entity",
                    "id": "character-lin-lan",
                    "title": "林澜",
                    "content": "林澜是曦环深空港的调度官，做决定前会核对原始航行日志。",
                    "entity_type": "character",
                    "attributes": {"pronouns": "她"},
                    "source_refs": [{"kind": "user", "ref": "protected-test-brief"}],
                },
            },
            {
                "operation": "upsert",
                "record": {
                    "kind": "event",
                    "id": "event-quantum-beacon",
                    "title": "量子信标重现",
                    "content": "未知量子信标在午夜重现，其频率与二十年前失踪的长夜号完全一致。",
                    "occurred_at": "2387-08-12T00:00:00Z",
                    "attributes": {},
                    "source_refs": [{"kind": "user", "ref": "protected-test-brief"}],
                },
            },
            {
                "operation": "upsert",
                "record": {
                    "kind": "constraint",
                    "id": "constraint-no-corona",
                    "title": "不得接近日冕层",
                    "content": "所有飞船都不得接近日冕层，故事结局也不能违反此限制。",
                    "severity": "required",
                    "attributes": {},
                    "source_refs": [{"kind": "user", "ref": "protected-test-brief"}],
                },
            },
        ]
        proposed_knowledge = await user.post(
            f"/api/projects/{project_id}/memory/changes",
            headers=csrf_headers(user),
            json={
                "instruction": "Add the protected creation knowledge records.",
                "operations": records,
            },
        )
        assert proposed_knowledge.status_code == 201, proposed_knowledge.text
        knowledge_run_id = proposed_knowledge.json()["id"]
        accepted_knowledge = await user.post(
            f"/api/projects/{project_id}/agent/runs/{knowledge_run_id}/review",
            headers=csrf_headers(user),
            json={"decision": "accept"},
        )
        assert accepted_knowledge.status_code == 200, accepted_knowledge.text
        assert accepted_knowledge.json()["status"] == "completed"

        creation = await user.post(
            f"/api/projects/{project_id}/agent/runs",
            headers=csrf_headers(user),
            json={
                "mode": "write",
                "model": model,
                "effort": "low",
                "instruction": (
                    "使用 character-lin-lan、event-quantum-beacon 和 constraint-no-corona "
                    "创作一个完整的中文科幻短篇。必须把大纲写入 outline.md，把正文写入 "
                    "chapters/beacon.md；正文必须明确应用三条知识，完成结果的 "
                    "used_knowledge_ids 必须列出这三个稳定 ID。"
                ),
                "target_refs": ["intent.md", "rules.md"],
            },
        )
        assert creation.status_code == 202, creation.text
        run_id = creation.json()["id"]

        deadline = asyncio.get_running_loop().time() + 1200
        while True:
            state = await user.get(f"/api/projects/{project_id}/agent/runs/{run_id}")
            assert state.status_code == 200, state.text
            run = state.json()
            if run["status"] in {
                "awaiting_review",
                "completed",
                "failed",
                "cancelled",
                "conflicted",
            }:
                break
            assert asyncio.get_running_loop().time() < deadline, f"Run timed out: {run}"
            await asyncio.sleep(3)
        assert run["status"] == "awaiting_review", run
        assert {
            "character-lin-lan",
            "event-quantum-beacon",
            "constraint-no-corona",
        } <= set(run["final_output"]["used_knowledge_ids"])

        change_response = await user.get(
            f"/api/projects/{project_id}/agent/runs/{run_id}/changes"
        )
        assert change_response.status_code == 200
        changes = change_response.json()
        changed_paths = {item["path"] for item in changes["files"]}
        assert {"outline.md", "chapters/beacon.md"} <= changed_paths
        assert changes["validation"]["passed"] is True
        assert changes["self_review"]["summary"]

        replay = await user.get(
            f"/api/projects/{project_id}/agent/runs/{run_id}/events",
            headers={"Last-Event-ID": "1"},
        )
        assert replay.status_code == 200, replay.text
        assert "id: 1\n" not in replay.text
        assert "awaiting_review" in replay.text

        accepted = await user.post(
            f"/api/projects/{project_id}/agent/runs/{run_id}/review",
            headers=csrf_headers(user),
            json={"decision": "accept"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "completed"
        assert accepted.json()["result_revision_id"] != base_revision_id
        project_after = (await user.get(f"/api/projects/{project_id}")).json()
        assert project_after["active_revision_id"] == accepted.json()["result_revision_id"]
        outline = await user.get(
            f"/api/projects/{project_id}/files/content",
            params={"path": "outline.md"},
        )
        chapter = await user.get(
            f"/api/projects/{project_id}/files/content",
            params={"path": "chapters/beacon.md"},
        )
        assert outline.status_code == 200
        assert chapter.status_code == 200
        chapter_content = chapter.json()["content"]
        assert "林澜" in chapter_content
        assert "日冕层" in chapter_content
