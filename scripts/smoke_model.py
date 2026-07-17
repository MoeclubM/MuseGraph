"""通用冒烟: model + effort 创作 检查 sm | ch | token"""
import json, os, sys, time, urllib.request

API = os.environ.get("E2E_API_URL", "http://127.0.0.1:4080")
EMAIL = "admin@example.com"
PASSWORD = "Admin123!Pass"
MODEL = os.environ.get("SMOKE_MODEL", "mimo-v2.5")
EFFORT = os.environ.get("SMOKE_EFFORT", "medium")
POLL = float(os.environ.get("AGENT_MONITOR_POLL_SEC", "5"))
TIMEOUT = float(os.environ.get("AGENT_MONITOR_TIMEOUT_SEC", "1200"))

def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}

def fmt(v):
    if v is None: return "N/A"
    if isinstance(v, (int, float)) and v > 0: return str(round(v))
    return str(v)[:80]

def main():
    for _ in range(30):
        try: urllib.request.urlopen(API + "/api/health", timeout=5); break
        except Exception: time.sleep(2)
    else: print("FATAL", file=sys.stderr); return 2

    tok = req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})["token"]
    proj = req("POST", "/api/projects", {"title": f"SMOKE {MODEL} {EFFORT} {int(time.time())}", "description": "smoke"}, tok)
    pid = proj["id"]
    pr = req("GET", f"/api/projects/{pid}", token=tok)
    cm = dict(pr.get("component_models") or {})
    cm["operation_agent_task"] = MODEL
    cm["memory_build"] = MODEL
    req("PUT", f"/api/projects/{pid}", {"component_models": cm}, tok)

    prompt = "请创作约800字的短篇文本。先调用store_structured_memory写入结构化记忆(字段自行决定),再调用write_document_unit写入正文,最后调用build_project_memory。自行调用工具,勿向用户提问。"
    body = {"message": prompt, "model": MODEL}
    if EFFORT and EFFORT != "none": body["effort"] = EFFORT

    started = req("POST", f"/api/projects/{pid}/agent/chat", body, tok)
    sid = started["session_id"]
    print(f"MODEL={MODEL} EFFORT={EFFORT} session={sid} project={pid}", flush=True)

    deadline = time.time() + TIMEOUT
    last_steps = -1
    while time.time() < deadline:
        det = req("GET", f"/api/projects/{pid}/agent/chat/{sid}", token=tok)
        status = str(det.get("status") or "").lower()
        steps = det.get("steps") or []
        if len(steps) != last_steps:
            last_steps = len(steps)
            for st in steps[-5:]:
                preview = (st.get("tool_result_preview") or st.get("message") or "")[:80]
                print(time.strftime("%H:%M:%S"), st.get("step_type"), st.get("status"), preview, flush=True)
        if status in ("completed", "partial", "failed"):
            pr = req("GET", f"/api/projects/{pid}", token=tok)
            ws = (pr.get("creative_state") or {}).get("agent_workspace") or {}
            ch = pr.get("chapters") or []
            chars = sum(len(str(c.get("content") or "")) for c in ch)
            sm = ws.get("structured_memory")
            sm_keys = list(sm.keys()) if isinstance(sm, dict) else "N/A"
            usage = det.get("usage") or {}
            in_tok = usage.get("input_tokens") or det.get("total_input_tokens")
            out_tok = usage.get("output_tokens") or det.get("total_output_tokens")
            thinking = ""
            thinking_steps = []
            for s in steps:
                t = s.get("thinking") or s.get("reasoning") or ""
                if t: thinking_steps.append(t)
            if thinking_steps: thinking = " | ".join(t[:40] for t in thinking_steps[-3:])

            print("--- RESULT ---")
            print(f"STATUS={status} steps={len(steps)}")
            print(f"SM          = {bool(sm)}  keys={sm_keys}")
            print(f"CH          = {len(ch)}  chars={chars}")
            print(f"TOKEN_IN    = {fmt(in_tok)}")
            print(f"TOKEN_OUT   = {fmt(out_tok)}")
            print(f"THINKING    = {thinking if thinking else 'N/A'}")
            print(f"EFFORT_USED = {det.get('effort') or det.get('reasoning_effort') or 'N/A'}")
            ok = status in ("completed", "partial") and bool(sm) and chars >= 200
            print(f"PASS: {ok}")
            return 0 if ok else 1
        time.sleep(POLL)
    print("TIMEOUT", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
