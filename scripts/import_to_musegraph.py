#!/usr/bin/env python3
"""
Import standalone engine results into MuseGraph Docker backend.
Creates projects and chapters via the MuseGraph REST API.
"""
import json
import re
import sys
from pathlib import Path

import httpx

BASE_URL = "http://172.30.6.86:3010/api"
EMAIL = "admin@example.com"
PASSWORD = "Admin123!Pass"
RUN_DIR = Path(r"C:\Users\QwQ\Documents\GitHub\MuseGraph\.musegraph\creative-run\20260607175914")


def login() -> str:
    r = httpx.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    token = r.json()["token"]
    print(f"  Logged in, token: {token[:20]}...")
    return token


def create_project(token: str, title: str, description: str, creative_state: dict | None = None) -> str:
    body = {
        "title": title,
        "description": description,
        "visibility": "private",
    }
    if creative_state:
        body["creative_state"] = creative_state
    r = httpx.post(
        f"{BASE_URL}/projects",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    project_id = data["id"]
    print(f"  Created project: {title} (id={project_id[:12]}...)")
    return project_id


def delete_default_chapter(token: str, project_id: str):
    """Delete the auto-created 'Main Draft' chapter."""
    r = httpx.get(
        f"{BASE_URL}/projects/{project_id}/chapters",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    chapters = r.json()
    if chapters and len(chapters) == 1 and chapters[0].get("title") == "Main Draft":
        ch_id = chapters[0]["id"]
        return ch_id
    return None


def create_chapter(token: str, project_id: str, title: str, content: str, order: int, status: str = "final") -> str:
    r = httpx.post(
        f"{BASE_URL}/projects/{project_id}/chapters",
        json={
            "title": title,
            "content": content,
            "status": status,
            "order_index": order,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    ch_id = r.json()["id"]
    return ch_id


def load_chapters(directory: Path, prefix: str = "chapter") -> list[dict]:
    """Load chapter files from a directory."""
    chapters = []
    pattern = re.compile(rf"{prefix}-(\d+)\.md")
    for f in sorted(directory.glob(f"{prefix}-*.md")):
        m = pattern.match(f.name)
        if m:
            idx = int(m.group(1))
            text = f.read_text(encoding="utf-8")
            lines = text.split("\n", 1)
            title = lines[0].lstrip("#").strip()
            content = lines[1].strip() if len(lines) > 1 else text
            chapters.append({"index": idx, "title": title, "content": content})
    return chapters


def import_scenario(token: str, name: str, directory: Path, prefix: str, project_title: str, description: str, creative_state: dict | None = None):
    """Import a scenario's chapters into a MuseGraph project."""
    print(f"\n{'='*60}")
    print(f"Importing: {name}")
    print(f"{'='*60}")

    if not directory.exists():
        print(f"  SKIP: directory not found: {directory}")
        return

    chapters = load_chapters(directory, prefix)
    if not chapters:
        print(f"  SKIP: no {prefix} files found")
        return

    total_chars = sum(len(ch["content"]) for ch in chapters)
    print(f"  Found {len(chapters)} sections, {total_chars:,} chars")

    # Load structured memory for creative_state
    sm_file = directory / "structured_memory.json"
    if sm_file.exists() and not creative_state:
        try:
            creative_state = json.loads(sm_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Load knowledge graph info
    kg_file = directory / "knowledge_graph.json"
    kg_info = {}
    if kg_file.exists():
        try:
            kg_data = json.loads(kg_file.read_text(encoding="utf-8"))
            kg_info = {
                "graph_nodes": len(kg_data.get("nodes", [])),
                "graph_edges": len(kg_data.get("edges", [])),
            }
        except Exception:
            pass

    # Enrich creative_state with run info
    if creative_state is None:
        creative_state = {}
    creative_state.update({
        "engine": "musegraph_standalone_engine",
        "run_id": "20260607175914",
        "total_chars": total_chars,
        "sections_count": len(chapters),
        **kg_info,
    })

    # Create project
    project_id = create_project(token, project_title, description, creative_state)

    # Create chapters
    for i, ch in enumerate(chapters):
        ch_id = create_chapter(token, project_id, ch["title"], ch["content"], i, status="final")
        char_count = len(ch["content"])
        print(f"    [{i+1}/{len(chapters)}] {ch['title'][:40]} ({char_count:,} chars) -> OK")

    # Delete the auto-created default chapter (now we have our chapters)
    default_ch = delete_default_chapter(token, project_id)
    if default_ch:
        try:
            httpx.delete(
                f"{BASE_URL}/projects/{project_id}/chapters/{default_ch}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            print(f"  Deleted default 'Main Draft' chapter")
        except Exception:
            pass  # May fail if it's the only chapter at time of deletion

    print(f"  DONE: {name} imported as project {project_id[:12]}...")
    return project_id


def main():
    print("MuseGraph Import Tool")
    print(f"Source: {RUN_DIR}")
    print()

    token = login()

    # 1. Novel
    import_scenario(
        token, "Novel",
        RUN_DIR / "novel", "chapter",
        "记忆潮汐 — 20章科幻短篇小说",
        "Agent自主规划并生成的20章节短篇科幻小说。主题：记忆潮汐与城市自治AI的最后一次梦境审判。"
        "由Nemotron-3-Ultra模型生成，包含完整的知识图谱、结构化记忆和时间线。",
        creative_state={"text_type": "小说", "model": "nvidia/nemotron-3-ultra-550b-a55b:free"},
    )

    # 2. Product
    import_scenario(
        token, "Product",
        RUN_DIR / "product", "section",
        "MuseGraph 产品介绍 — 2万字商业文案",
        "Agent自主规划并生成的MuseGraph产品详细介绍长文（29,221字符）。"
        "涵盖用户痛点分析、架构能力详解、协作写作模式、权限体系、模型网关设计、"
        "记忆可视化系统、部署方案、安全合规策略、成功案例和购买转化引导。",
        creative_state={"text_type": "产品文档", "model": "mimo-v2.5"},
    )

    # 3. Resume
    import_scenario(
        token, "Resume",
        RUN_DIR / "resume", "section",
        "个人简历 — AI产品架构师（1万字）",
        "Agent自主规划并生成的个人简历/履历文档（19,094字符）。"
        "候选人定位为AI产品架构师与全栈工程负责人，包含可验证成果、"
        "项目经历、能力证据、技能图谱和岗位匹配叙事。",
        creative_state={"text_type": "简历", "model": "mimo-v2.5"},
    )

    print(f"\n{'='*60}")
    print("ALL IMPORTS COMPLETE")
    print(f"{'='*60}")
    print(f"Open http://172.30.6.86:3010 to view your projects!")


if __name__ == "__main__":
    main()
