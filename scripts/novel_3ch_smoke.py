import json, os, sys, time, urllib.request
API = os.environ.get("E2E_API_URL", "http://127.0.0.1:4080")
MODEL = os.environ.get("PW_AGENT_MODEL", "mimo-v2.5")
POLL = float(os.environ.get("AGENT_MONITOR_POLL_SEC", "15"))
TIMEOUT = float(os.environ.get("AGENT_MONITOR_TIMEOUT_SEC", "1800"))

def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=180) as resp:
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
    tok = req("POST", "/api/auth/login", {"email": "admin@example.com", "password": "Admin123!Pass"})["token"]
    proj = req("POST", "/api/projects", {"title": f"沙雕科幻3章 {int(time.time())}", "description": "沙雕科幻多章节验证"}, tok)
    pid = proj["id"]
    pr = req("GET", f"/api/projects/{pid}", token=tok)
    cm = dict(pr.get("component_models") or {})
    cm["operation_agent_task"] = MODEL
    cm["memory_build"] = MODEL
    req("PUT", f"/api/projects/{pid}", {"component_models": cm}, tok)
    prompt = (
        "请创作一部沙雕风格的科幻长篇小说，先写前3章。要求：\n"
        "1) 先用 store_structured_memory 写入世界观、主要角色、全书大纲（至少30章规划）；\n"
        "2) 然后用 write_document_unit 逐章写入前3章正文，每章约1500字，章节标题形如「第X章 标题」；\n"
        "3) 最后调用 build_project_memory。\n"
        "风格：沙雕、脑洞大开、幽默吐槽，但科幻设定自洽。自行调用工具，勿向用户提问。"
    )
    started = req("POST", f"/api/projects/{pid}/agent/chat", {"message": prompt, "model": MODEL}, tok)
    sid = started["session_id"]
    print(f"session={sid} project={pid}", flush=True)
    deadline = time.time() + TIMEOUT
    last_steps = -1
    while time.time() < deadline:
        det = req("GET", f"/api/projects/{pid}/agent/chat/{sid}", token=tok)
        status = str(det.get("status") or "").lower()
        steps = det.get("steps") or []
        if len(steps) != last_steps:
            last_steps = len(steps)
            for st in steps[-5:]:
                prev = (st.get("tool_result_preview") or st.get("message") or "")[:70]
                print(time.strftime("%H:%M:%S"), st.get("step_type"), st.get("status"), prev, flush=True)
        if status in ("completed", "partial", "failed"):
            pr = req("GET", f"/api/projects/{pid}", token=tok)
            ws = (pr.get("creative_state") or {}).get("agent_workspace") or {}
            ch = pr.get("chapters") or []
            chars = sum(len(str(c.get("content") or "")) for c in ch)
            sm = ws.get("structured_memory")
            ok = status in ("completed", "partial") and (bool(sm) or chars >= 300)
            print("--- RESULT ---", flush=True)
            print(f"status={status} steps={len(steps)} sm={bool(sm)} ch={len(ch)} chars={chars} {'PASS' if ok else 'FAIL'}", flush=True)
            for c in sorted(ch, key=lambda x: x.get("order_index", 0)):
                print(f"  ch{c.get('order_index')} {c.get('title')} {len(c.get('content') or '')}字", flush=True)
            return 0 if ok else 1
        time.sleep(POLL)
    print("timeout", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
