#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4080"


def req(method: str, path: str, data=None, token: str | None = None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    _, login = req("POST", "/api/auth/login", {"email": "admin@example.com", "password": "Admin123!Pass"})
    token = login["token"]
    print("login ok")

    _, projects = req("GET", "/api/projects", token=token)
    if not projects:
        print("no projects")
        return 1
    pid = projects[0]["id"]
    print("project", pid)

    _, sessions = req("GET", f"/api/projects/{pid}/agent/sessions", token=token)
    print("agent sessions", len(sessions))

    try:
        _, suggest = req(
            "POST",
            f"/api/projects/{pid}/agent/suggest",
            {"editor_text": "夜色降临，主角站在城墙上望着远方。", "cursor_position": 18},
            token=token,
        )
        print("suggest count", len(suggest.get("suggestions", [])))
    except urllib.error.HTTPError as exc:
        print("suggest", exc.code, exc.read().decode()[:300])

    try:
        _, chat = req(
            "POST",
            f"/api/projects/{pid}/agent/chat",
            {"message": "分析当前项目并规划记忆结构"},
            token=token,
        )
        print("chat session", chat.get("session_id"))
    except urllib.error.HTTPError as exc:
        print("chat", exc.code, exc.read().decode()[:300])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())