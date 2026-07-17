import io
import os
import secrets
import zipfile

import httpx
import pytest


pytestmark = pytest.mark.integration
BASE_URL = os.environ.get("MUSEGRAPH_TEST_BASE_URL")
ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD")


def csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["musegraph_csrf"]}


async def register(client: httpx.AsyncClient, label: str) -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{label}-{secrets.token_hex(6)}@example.com",
            "password": "Integration-Test-Password-2026!",
            "nickname": label,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert "token" not in payload
    assert client.cookies.get("musegraph_session")
    assert client.cookies.get("musegraph_csrf")
    return payload["user"]


@pytest.mark.asyncio
async def test_real_platform_security_skills_versions_and_tenant_isolation():
    assert BASE_URL, "MUSEGRAPH_TEST_BASE_URL is required for integration tests"
    assert ADMIN_EMAIL, "SEED_ADMIN_EMAIL is required for integration tests"
    assert ADMIN_PASSWORD, "SEED_ADMIN_PASSWORD is required for integration tests"
    timeout = httpx.Timeout(600)
    async with (
        httpx.AsyncClient(base_url=BASE_URL, timeout=timeout) as owner,
        httpx.AsyncClient(base_url=BASE_URL, timeout=timeout) as viewer,
        httpx.AsyncClient(base_url=BASE_URL, timeout=timeout) as admin,
    ):
        health = await owner.get("/api/health")
        assert health.json() == {"status": "ok"}
        assert health.headers["x-content-type-options"] == "nosniff"
        assert health.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in health.headers["content-security-policy"]

        owner_user = await register(owner, "owner")
        viewer_user = await register(viewer, "viewer")

        missing_csrf = await owner.post(
            "/api/projects",
            json={"title": "Must fail without CSRF"},
        )
        assert missing_csrf.status_code == 403

        created = await owner.post(
            "/api/projects",
            headers=csrf_headers(owner),
            json={
                "title": "Integration project",
                "description": "Real PostgreSQL, Redis, Git, and Cognee",
                "pack_slug": "novel",
                "component_models": {},
            },
        )
        assert created.status_code == 201, created.text
        project = created.json()
        project_id = project["id"]
        initial_revision_id = project["active_revision_id"]

        knowledge = await owner.get(f"/api/projects/{project_id}/memory")
        assert knowledge.status_code == 200, knowledge.text
        assert knowledge.json()["records"] == []
        initial_dataset = knowledge.json()["dataset_name"]

        traversing = await owner.post(
            f"/api/projects/{project_id}/files/manual",
            headers=csrf_headers(owner),
            json={"path": "../escape.md", "content": "escape"},
        )
        assert traversing.status_code == 400

        unsafe_png = await owner.post(
            f"/api/projects/{project_id}/files",
            headers=csrf_headers(owner),
            files={"file": ("fake.png", b"not a png", "image/png")},
        )
        assert unsafe_png.status_code == 400

        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "A" * (1024 * 1024))
        archive_bytes.seek(0)
        compressed_bomb = await owner.post(
            f"/api/projects/{project_id}/files",
            headers=csrf_headers(owner),
            files={
                "file": (
                    "compressed.docx",
                    archive_bytes.getvalue(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert compressed_bomb.status_code == 400

        markdown = await owner.post(
            f"/api/projects/{project_id}/files/manual",
            headers=csrf_headers(owner),
            json={
                "path": "chapters/one.md",
                "content": "# One\n\n<img src=x onerror=window.__musegraph_xss=true>",
            },
        )
        assert markdown.status_code == 201, markdown.text

        add_viewer = await owner.post(
            f"/api/projects/{project_id}/members",
            headers=csrf_headers(owner),
            json={"user_id": viewer_user["id"], "role": "viewer"},
        )
        assert add_viewer.status_code == 201, add_viewer.text
        assert (await viewer.get(f"/api/projects/{project_id}")).status_code == 200
        forbidden_write = await viewer.post(
            f"/api/projects/{project_id}/files/manual",
            headers=csrf_headers(viewer),
            json={"path": "viewer.md", "content": "forbidden"},
        )
        assert forbidden_write.status_code == 403

        custom_skill = {
            "slug": "project-voice",
            "name": "Project Voice",
            "description": "Project-local voice constraints",
            "instructions": "Use concise present-tense prose.",
            "scopes": ["write"],
            "roles": ["writer"],
            "allowed_tools": ["list_files", "read_file", "write_file"],
            "params_schema": {
                "type": "object",
                "properties": {"tone": {"type": "string"}},
                "additionalProperties": False,
            },
            "enabled": True,
        }
        skill_response = await owner.post(
            f"/api/projects/{project_id}/skills",
            headers=csrf_headers(owner),
            json=custom_skill,
        )
        assert skill_response.status_code == 201, skill_response.text
        preview = await owner.get(
            f"/api/projects/{project_id}/skills/resolve/preview",
            params={"operation": "write", "role": "writer", "slug": "project-voice"},
        )
        assert preview.status_code == 200
        assert preview.json()["source"] == "project"

        second_project_response = await owner.post(
            "/api/projects",
            headers=csrf_headers(owner),
            json={"title": "Isolated project", "pack_slug": "generic"},
        )
        assert second_project_response.status_code == 201, second_project_response.text
        second_project_id = second_project_response.json()["id"]
        isolated_preview = await owner.get(
            f"/api/projects/{second_project_id}/skills/resolve/preview",
            params={"operation": "write", "role": "writer", "slug": "project-voice"},
        )
        assert isolated_preview.status_code == 422
        assert (await viewer.get(f"/api/projects/{second_project_id}")).status_code == 403

        versions = (
            await owner.get(f"/api/projects/{project_id}/versions")
        ).json()
        root_revision = next(item for item in versions if item["id"] == initial_revision_id)
        current_revision_id = next(item for item in versions if item["status"] == "active")["id"]

        rejected_restore = await owner.post(
            f"/api/projects/{project_id}/versions/restore",
            headers=csrf_headers(owner),
            json={"revision_id": root_revision["id"]},
        )
        assert rejected_restore.status_code == 201, rejected_restore.text
        rejected_run = rejected_restore.json()
        changes = await owner.get(
            f"/api/projects/{project_id}/agent/runs/{rejected_run['id']}/changes"
        )
        assert changes.status_code == 200
        assert changes.json()["files"]
        rejected = await owner.post(
            f"/api/projects/{project_id}/agent/runs/{rejected_run['id']}/review",
            headers=csrf_headers(owner),
            json={"decision": "reject"},
        )
        assert rejected.json()["status"] == "rejected"
        assert (await owner.get(f"/api/projects/{project_id}")).json()["active_revision_id"] == current_revision_id

        conflicted_restore = await owner.post(
            f"/api/projects/{project_id}/versions/restore",
            headers=csrf_headers(owner),
            json={"revision_id": root_revision["id"]},
        )
        conflict_run = conflicted_restore.json()
        later_edit = await owner.post(
            f"/api/projects/{project_id}/files/manual",
            headers=csrf_headers(owner),
            json={"path": "chapters/two.md", "content": "# Two"},
        )
        assert later_edit.status_code == 201, later_edit.text
        conflicted = await owner.post(
            f"/api/projects/{project_id}/agent/runs/{conflict_run['id']}/review",
            headers=csrf_headers(owner),
            json={"decision": "accept"},
        )
        assert conflicted.json()["status"] == "conflicted"

        accepted_restore = await owner.post(
            f"/api/projects/{project_id}/versions/restore",
            headers=csrf_headers(owner),
            json={"revision_id": root_revision["id"]},
        )
        accepted_run = accepted_restore.json()
        accepted = await owner.post(
            f"/api/projects/{project_id}/agent/runs/{accepted_run['id']}/review",
            headers=csrf_headers(owner),
            json={"decision": "accept"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "completed"
        assert accepted.json()["result_revision_id"]
        restored_project = (await owner.get(f"/api/projects/{project_id}")).json()
        assert restored_project["active_revision_id"] == accepted.json()["result_revision_id"]
        restored_knowledge = (await owner.get(f"/api/projects/{project_id}/memory")).json()
        assert restored_knowledge["dataset_name"] != initial_dataset
        assert restored_knowledge["records"] == []
        assert not any(
            item["path"] in {"chapters/one.md", "chapters/two.md"}
            for item in (await owner.get(f"/api/projects/{project_id}/files")).json()["files"]
        )

        admin_login = await admin.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert admin_login.status_code == 200, admin_login.text
        runtime_health = await admin.get("/api/admin/runtime-health")
        assert runtime_health.status_code == 200, runtime_health.text
        assert runtime_health.json()["database"] == "ok"
        assert runtime_health.json()["redis"] == "ok"
        audit_logs = await admin.get(
            "/api/admin/audit-logs",
            params={"project_id": project_id, "limit": 1000},
        )
        assert audit_logs.status_code == 200, audit_logs.text
        actions = {entry["action"] for entry in audit_logs.json()["items"]}
        assert "agent.run.accept" in actions
        assert "agent.run.reject" in actions

        password_change = await viewer.post(
            "/api/auth/change-password",
            headers=csrf_headers(viewer),
            json={
                "current_password": "Integration-Test-Password-2026!",
                "new_password": "Integration-Test-Password-Changed-2026!",
            },
        )
        assert password_change.status_code == 204
        assert (await viewer.get("/api/auth/me")).status_code == 401
        assert owner_user["id"] != viewer_user["id"]
