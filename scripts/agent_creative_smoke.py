"""API-only agent creative smoke."""
import json, os, sys, time, urllib.request
API = os.environ.get("E2E_API_URL", "http://127.0.0.1:4080")
EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin123!Pass")
MODEL = os.environ.get("PW_AGENT_MODEL", "mimo-v2.5")
POLL = float(os.environ.get("AGENT_MONITOR_POLL_SEC", "12"))
TIMEOUT = float(os.environ.get("AGENT_MONITOR_TIMEOUT_SEC", "1200"))

def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}

def main():
    for _ in range(30):
        try:
            urllib.request.urlopen(API + "/api/health", timeout=5)
            break
        except Exception:
            time.sleep(2)
    else:
        print("API not ready", file=sys.stderr)
        return 2
    tok = req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})["token"]
    proj = req("POST", "/api/projects", {"title": f"Monitor smoke {int(time.time())}", "description": "smoke"}, tok)
    pid = proj["id"]
    pr = req("GET", f"/api/projects/{pid}", token=tok)
    cm = dict(pr.get("component_models") or {})
    cm["operation_agent_task"] = MODEL
    req("PUT", f"/api/projects/{pid}", {"component_models": cm}, tok)
    prompt = "请创作约800字科幻短篇，写入 structured_memory（世界观、角色、大纲）与一章正文。自行调用工具，勿向用户提问。"
    started = req("POST", f"/api/projects/{pid}/agent/chat", {"message": prompt, "model": MODEL}, tok)
    sid = started["session_id"]
    print(f"session={sid} project={pid}")
    deadline = time.time() + TIMEOUT
    last_steps = -1
    while time.time() < deadline:
        det = req("GET", f"/api/projects/{pid}/agent/chat/{sid}", token=tok)
        status = str(det.get("status") or "").lower()
        steps = det.get("steps") or []
        if len(steps) != last_steps:
            last_steps = len(steps)
            for st in steps[-4:]:
                print(time.strftime("%H:%M:%S"), st.get("step_type"), st.get("status"), (st.get("tool_result_preview") or st.get("message") or "")[:60])
        if status in ("completed", "partial", "failed"):
            pr = req("GET", f"/api/projects/{pid}", token=tok)
            ws = (pr.get("creative_state") or {}).get("agent_workspace") or {}
            ch = pr.get("chapters") or []
            chars = sum(len(str(c.get("content") or "")) for c in ch)
            sm = ws.get("structured_memory")
            print("--- RESULT ---")
            print("status", status, "steps", len(steps), "sm", bool(sm), "ch", len(ch), "chars", chars)
            return 0 if status in ("completed", "partial") and (bool(sm) or chars >= 300) else 1
        time.sleep(POLL)
    print("timeout", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
