#!/usr/bin/env python3
"""End-to-end verification: Pi agent creates a short novel with structured data (mimo model)."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4080"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gpt-5.5"
EMBEDDING_MODEL = sys.argv[3] if len(sys.argv) > 3 else "Qwen3-Embedding-0.6B"
RERANKER_MODEL = sys.argv[4] if len(sys.argv) > 4 else "Qwen3-Reranker-0.6B"
POLL_SECONDS = 5
TIMEOUT_SECONDS = 1800


def request(method: str, path: str, body=None, token: str | None = None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def main() -> int:
    print(f"API: {API_BASE}, model: {MODEL}")

    _, login = request("POST", "/api/auth/login", {"email": "admin@example.com", "password": "Admin123!Pass"})
    token = login["token"]
    print("login ok")

    _, project = request(
        "POST",
        "/api/projects",
        {"title": f"Agent Novel E2E {int(time.time())}", "description": "Pi agent verification"},
        token=token,
    )
    project_id = project["id"]
    print("project", project_id)

    # Prefer mimo model on agent component
    component_models = dict(project.get("component_models") or {})
    component_models["operation_agent_task"] = MODEL
    component_models["memory_build"] = MODEL
    component_models["memory_embedding"] = EMBEDDING_MODEL
    component_models["memory_reranker"] = RERANKER_MODEL
    request("PUT", f"/api/projects/{project_id}", {"component_models": component_models}, token=token)

    prompt = (
        "请创作一篇约2000字的短篇小说。你必须自行决定并生成结构化数据：世界观、主要角色、情节大纲、关键地点、时间线。"
        "执行步骤：1) 规划 memory_schema 2) store_structured_memory 写入结构化记忆与 graph "
        "3) generate 正文 4) write_chapter 写入章节。"
        "structured_memory 需包含 worldview、characters、plot_outline、locations、timeline 等字段。"
    )

    _, chat = request(
        "POST",
        f"/api/projects/{project_id}/agent/chat",
        {"message": prompt, "model": MODEL},
        token=token,
    )
    session_id = chat["session_id"]
    print("session", session_id)

    deadline = time.time() + TIMEOUT_SECONDS
    final_status = "unknown"
    session: dict = {}
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        _, session = request("GET", f"/api/projects/{project_id}/agent/chat/{session_id}", token=token)
        final_status = str(session.get("status") or "")
        print(f"  status={final_status}, steps={len(session.get('steps') or [])}, msgs={len(session.get('messages') or [])}")
        if final_status in {"completed", "failed", "partial"}:
            break

    _, project_data = request("GET", f"/api/projects/{project_id}", token=token)
    workspace = (project_data.get("creative_state") or {}).get("agent_workspace") or {}
    plan = session.get("plan") or {}
    structured = workspace.get("structured_memory") or plan.get("structured_memory") or {}
    graph = workspace.get("graph") or plan.get("graph") or {}

    checks = {
        "session_completed": final_status in {"completed", "partial"},
        "has_plan": bool(plan),
        "has_structured_memory": bool(structured),
        "has_graph": bool(graph.get("nodes") or graph.get("edges")),
        "has_worldview": any(k in structured for k in ("worldview", "world_view", "世界观")),
        "has_characters": any(k in structured for k in ("characters", "roles", "角色")),
        "has_plot": any(k in structured for k in ("plot_outline", "outline", "plot", "情节", "大纲")),
    }

    chapters = project_data.get("chapters") or []
    content_len = sum(len(str(ch.get("content") or "")) for ch in chapters)
    checks["has_chapter_content"] = content_len > 200

    print("\n=== Verification ===")
    ok = True
    for key, passed in checks.items():
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {key}")
        ok = ok and passed

    print(f"\nstructured_memory keys: {list(structured.keys()) if isinstance(structured, dict) else structured}")
    print(f"graph nodes: {len(graph.get('nodes') or [])}, edges: {len(graph.get('edges') or [])}")
    print(f"chapter content chars: {content_len}")

    if not ok:
        print("\nFAILED")
        return 1
    print("\nPASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
