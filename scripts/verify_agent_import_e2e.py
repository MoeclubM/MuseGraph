#!/usr/bin/env python3
"""API verification: import chapter -> agent analyze -> continue writing."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API_BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:3010"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gpt-5.5"
EMBEDDING_MODEL = sys.argv[3] if len(sys.argv) > 3 else "Qwen3-Embedding-0.6B"
RERANKER_MODEL = sys.argv[4] if len(sys.argv) > 4 else "Qwen3-Reranker-0.6B"
POLL_SECONDS = 5
TIMEOUT_SECONDS = 1800

SAMPLE_NOVEL = """《星港余烬》节选

公元2387年，人类在比邻星轨道建成了最后一座深空港口"曦环"。港口调度官林澜在值班夜发现一条未知量子信标，频率与二十年前失踪的探险舰"长夜号"一致。

信标解码后只有一句话："不要靠近日冕层。"林澜将情报同步给港口AI"赫斯提"，却收到相互矛盾的航行建议。维修工周原在废弃舱段找到长夜号船员陈默的私人日志，日志显示他们并非失踪，而是在尝试封印一种会吞噬光子的微观结构。

与此同时，港口商业代表艾琳坚持提前启动跃迁窗口，否则将损失三千万信用点。林澜必须在六小时内决定是否推迟跃迁、是否公开日志，以及是否相信一个已经"死去"的船员留下的警告。"""


def request(method: str, path: str, body=None, token: str | None = None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def wait_session(token: str, project_id: str, session_id: str, label: str) -> dict:
    deadline = time.time() + TIMEOUT_SECONDS
    last_status = "unknown"
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        _, session = request(
            "GET",
            f"/api/projects/{project_id}/agent/chat/{session_id}",
            token=token,
        )
        last_status = str(session.get("status") or "")
        steps = len(session.get("steps") or [])
        print(f"  [{label}] status={last_status}, steps={steps}")
        if last_status in {"completed", "failed", "partial"}:
            return session
    raise RuntimeError(f"{label} timed out (last status: {last_status})")


def main() -> int:
    print(f"API: {API_BASE}, model: {MODEL}")

    _, login = request("POST", "/api/auth/login", {"email": "admin@example.com", "password": "Admin123!Pass"})
    token = login["token"]
    print("login ok")

    _, project = request(
        "POST",
        "/api/projects",
        {"title": f"Import Agent E2E {int(time.time())}", "description": "import analyze verify"},
        token=token,
    )
    project_id = project["id"]
    component_models = dict(project.get("component_models") or {})
    component_models["operation_agent_task"] = MODEL
    component_models["memory_build"] = MODEL
    component_models["memory_embedding"] = EMBEDDING_MODEL
    component_models["memory_reranker"] = RERANKER_MODEL
    request("PUT", f"/api/projects/{project_id}", {"component_models": component_models}, token=token)
    print("project", project_id)

    request(
        "POST",
        f"/api/projects/{project_id}/chapters",
        {"title": "星港余烬 节选", "content": SAMPLE_NOVEL},
        token=token,
    )
    print("chapter imported")

    analyze_prompt = (
        "请分析项目中已导入的章节《星港余烬 节选》，自行决定需要提取的结构化元素（世界观、角色、地点、时间线、冲突、伏笔等），"
        "写入 structured_memory 与 graph，并给出续写建议。优先读取章节内容，不要重复粘贴原文。"
    )
    _, analyze_chat = request(
        "POST",
        f"/api/projects/{project_id}/agent/chat",
        {"message": analyze_prompt, "model": MODEL},
        token=token,
    )
    analyze_session_id = analyze_chat["session_id"]
    print("analyze session", analyze_session_id)
    analyze_session = wait_session(token, project_id, analyze_session_id, "analyze")
    if str(analyze_session.get("status")) not in {"completed", "partial"}:
        print("analyze failed:", analyze_session.get("status"))
        return 1

    continue_prompt = (
        "基于你刚才的分析结果与 structured_memory，续写下一章（约800字）。"
        "保持角色口吻一致，引用已提取的时间线与地点设定，并将续写内容写入章节。"
    )
    _, continue_chat = request(
        "POST",
        f"/api/projects/{project_id}/agent/chat",
        {"message": continue_prompt, "model": MODEL},
        token=token,
    )
    continue_session_id = continue_chat["session_id"]
    print("continue session", continue_session_id)
    continue_session = wait_session(token, project_id, continue_session_id, "continue")
    if str(continue_session.get("status")) not in {"completed", "partial"}:
        print("continue failed:", continue_session.get("status"))
        return 1

    _, project_data = request("GET", f"/api/projects/{project_id}", token=token)
    workspace = (project_data.get("creative_state") or {}).get("agent_workspace") or {}
    structured = workspace.get("structured_memory") or {}
    chapters = project_data.get("chapters") or []
    all_text = "\n".join(str(ch.get("content") or "") for ch in chapters)

    checks = {
        "analyze_completed": str(analyze_session.get("status")) in {"completed", "partial"},
        "continue_completed": str(continue_session.get("status")) in {"completed", "partial"},
        "has_structured_memory": bool(structured),
        "has_prose": len(all_text) > 500,
    }
    print("\n=== Verification ===")
    failed = False
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        failed = failed or not ok

    print(f"structured_memory keys: {list(structured.keys()) if isinstance(structured, dict) else structured}")
    print(f"chapter chars: {len(all_text)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
