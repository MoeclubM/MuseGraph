"""Poll agent sessions until terminal or timeout."""
import json
import os
import sys
import time
import urllib.request

API = os.environ.get("E2E_API_URL", "http://127.0.0.1:4080")
EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin123!Pass")
POLL = float(os.environ.get("AGENT_MONITOR_POLL_SEC", "15"))
TIMEOUT = float(os.environ.get("AGENT_MONITOR_TIMEOUT_SEC", "1800"))


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.load(resp)


def main():
    tok = req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})["token"]
    deadline = time.time() + TIMEOUT
    watch = os.environ.get("AGENT_WATCH_SESSION", "").strip()
    while time.time() < deadline:
        projs = req("GET", "/api/projects", token=tok)
        running = []
        for p in projs:
            pid = p["id"]
            try:
                sess_list = req("GET", f"/api/projects/{pid}/agent/sessions", token=tok)
            except Exception as e:
                print("sessions err", pid[:8], e)
                continue
            for s in sess_list:
                sid = s.get("session_id")
                st = str(s.get("status") or "").lower()
                if watch and sid != watch:
                    continue
                if st in ("running", "pending"):
                    det = req("GET", f"/api/projects/{pid}/agent/chat/{sid}", token=tok)
                    steps = len(det.get("steps") or [])
                    last = (det.get("steps") or [])[-1] if steps else {}
                    print(
                        time.strftime("%H:%M:%S"),
                        st,
                        (det.get("title") or "")[:40],
                        f"steps={steps}",
                        last.get("step_type"),
                        last.get("status"),
                        (det.get("updated_at") or "")[-19:],
                        flush=True,
                    )
                    running.append(sid)
                elif watch and sid == watch:
                    print(time.strftime("%H:%M:%S"), "DONE", st, sid[:8], flush=True)
                    return 0
        if watch and not any(True for _ in [1]):
            # check if watch session exists and terminal
            pass
        if not running and not watch:
            print(time.strftime("%H:%M:%S"), "no running sessions", flush=True)
            return 0
        time.sleep(POLL)
    print("monitor timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
