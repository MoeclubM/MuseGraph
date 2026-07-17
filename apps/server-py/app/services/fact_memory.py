from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.project import ProjectFact, TextProject
from app.services.ai import call_llm, llm_billing_scope, require_structured_json_model, resolve_explicit_component_model
from app.services.creative_workflow import (
    chapter_has_memory_material,
    chapter_memory_text,
    project_creative_state_text,
    sorted_project_chapters,
)
from app.services.llm_json import extract_json_object
from app.services.memory_service import build_memory, delete_memory, get_memory_visualization
from app.services.ontology import build_memory_input_with_ontology, generate_ontology
from app.services.project_workspace import write_project_workspace_version_snapshot
from app.services.task_state import TaskStatus, task_manager


FACT_SYNC_TASK_TYPE = "fact_memory_sync"


def fact_content_hash(title: str, content: str, source_kind: str, source_ref: dict[str, Any] | None) -> str:
    payload = {
        "title": str(title or "").strip(),
        "content": str(content or "").strip(),
        "source_kind": str(source_kind or "").strip(),
        "source_ref": source_ref or {},
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def apply_fact_hash(fact: ProjectFact) -> None:
    fact.content_hash = fact_content_hash(fact.title, fact.content, fact.source_kind, fact.source_ref)


def _fact_memory_text(fact: ProjectFact) -> str:
    lines = [
        "[Project Fact]",
        f"ID: {fact.id}",
        f"Title: {fact.title}",
        f"Source: {fact.source_kind}",
    ]
    if fact.source_ref:
        lines.extend(["", "[Source Ref]", json.dumps(fact.source_ref, ensure_ascii=False, sort_keys=True)])
    lines.extend(["", "[Fact Content]", fact.content])
    if fact.entities:
        lines.extend(["", "[Extracted Entities]", json.dumps(fact.entities, ensure_ascii=False, sort_keys=True)])
    if fact.relationships:
        lines.extend(["", "[Extracted Relationships]", json.dumps(fact.relationships, ensure_ascii=False, sort_keys=True)])
    return "\n".join(lines).strip()


def _compose_project_memory_text(project: TextProject, facts: list[ProjectFact]) -> str:
    sections: list[str] = []
    for fact in facts:
        sections.append(_fact_memory_text(fact))
    for chapter in sorted_project_chapters(project):
        if chapter_has_memory_material(chapter):
            sections.append(chapter_memory_text(chapter))
    creative_state_text = project_creative_state_text(project)
    if creative_state_text:
        sections.append(creative_state_text)
    return "\n\n".join(section for section in sections if section.strip()).strip()


def _require_fact_sync_models(project: TextProject) -> tuple[str, str, str, str]:
    ontology_model = resolve_explicit_component_model(project, "ontology_generation")
    agent_model = resolve_explicit_component_model(project, "operation_agent_task")
    memory_model = resolve_explicit_component_model(project, "memory_build")
    embedding_model = resolve_explicit_component_model(project, "memory_embedding")
    missing = [
        name for name, value in (
            ("ontology_generation", ontology_model),
            ("operation_agent_task", agent_model),
            ("memory_build", memory_model),
            ("memory_embedding", embedding_model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Fact memory sync requires project component models: " + ", ".join(missing))
    return ontology_model, agent_model, memory_model, embedding_model


async def _extract_fact_graph(
    *,
    facts: list[ProjectFact],
    ontology: dict[str, Any],
    model: str,
    project: TextProject,
    db: AsyncSession,
) -> dict[str, Any]:
    facts_payload = [
        {
            "fact_id": fact.id,
            "title": fact.title,
            "content": fact.content,
            "source_kind": fact.source_kind,
        }
        for fact in facts
    ]
    selected_model = require_structured_json_model(model, "Fact graph extraction")
    prompt = (
        "Return valid JSON only. Extract entities and relationships from project facts.\n"
        "Entities may be people, objects, events, places, organizations, concepts, or other ontology-defined types.\n"
        "Use the provided ontology names when possible. Do not invent facts beyond the source text.\n"
        "Required schema:\n"
        '{"facts":[{"fact_id":"...","entities":[{"id":"stable-name","name":"...","type":"PERSON|OBJECT|EVENT|...","summary":"..."}],'
        '"relationships":[{"source":"entity id or name","target":"entity id or name","type":"RELATION_TYPE","fact":"source evidence"}]}]}\n\n'
        "Ontology:\n"
        f"{json.dumps(ontology, ensure_ascii=False, sort_keys=True)}\n\n"
        "Facts:\n"
        f"{json.dumps(facts_payload, ensure_ascii=False, sort_keys=True)}"
    )
    with llm_billing_scope(user_id=project.user_id, project_id=project.id):
        llm_result = await call_llm(
            selected_model,
            prompt,
            db,
            max_tokens=8192,
            billing_user_id=project.user_id,
            billing_project_id=project.id,
            prefer_stream_override=False,
            minimum_timeout_seconds=300,
        )
    parsed = extract_json_object(str(llm_result.get("content") or ""))
    if not parsed or not isinstance(parsed.get("facts"), list):
        raise RuntimeError("Fact graph extraction did not return the required facts array.")

    by_id = {fact.id: fact for fact in facts}
    seen_fact_ids: set[str] = set()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for item in parsed["facts"]:
        if not isinstance(item, dict):
            raise TypeError("Fact graph extraction item is not an object")
        fact_id = str(item.get("fact_id") or "").strip()
        fact = by_id.get(fact_id)
        if fact is None:
            raise RuntimeError(f"Fact graph extraction returned unknown fact_id: {fact_id}")
        seen_fact_ids.add(fact_id)
        entities = item.get("entities") if isinstance(item.get("entities"), list) else []
        relationships = item.get("relationships") if isinstance(item.get("relationships"), list) else []
        fact.entities = [entity for entity in entities if isinstance(entity, dict)]
        fact.relationships = [rel for rel in relationships if isinstance(rel, dict)]
        fact.ontology_snapshot = ontology
        fact.memory_status = "syncing"
        fact.memory_error = None

        fact_entity_names: dict[str, str] = {}
        for entity in fact.entities:
            raw_id = str(entity.get("id") or entity.get("name") or "").strip()
            if not raw_id:
                raise RuntimeError(f"Extracted entity for fact {fact_id} is missing id/name")
            fact_entity_names[str(entity.get("name") or raw_id).strip()] = raw_id
            if raw_id not in nodes:
                nodes[raw_id] = {
                    "id": raw_id,
                    "name": str(entity.get("name") or raw_id),
                    "type": str(entity.get("type") or "Entity"),
                    "summary": str(entity.get("summary") or ""),
                    "source_fact_ids": [fact_id],
                }
            elif fact_id not in nodes[raw_id]["source_fact_ids"]:
                nodes[raw_id]["source_fact_ids"].append(fact_id)
        for rel in fact.relationships:
            source = str(rel.get("source") or "").strip()
            target = str(rel.get("target") or "").strip()
            if not source or not target:
                raise RuntimeError(f"Extracted relationship for fact {fact_id} is missing source/target")
            source_id = source if source in nodes else fact_entity_names.get(source)
            target_id = target if target in nodes else fact_entity_names.get(target)
            if not source_id:
                raise RuntimeError(f"Extracted relationship for fact {fact_id} references unknown source entity: {source}")
            if not target_id:
                raise RuntimeError(f"Extracted relationship for fact {fact_id} references unknown target entity: {target}")
            edges.append({
                "source": source_id,
                "target": target_id,
                "type": str(rel.get("type") or rel.get("relation") or "RELATED_TO"),
                "fact": str(rel.get("fact") or ""),
                "source_fact_id": fact_id,
            })

    missing = sorted(set(by_id.keys()) - seen_fact_ids)
    if missing:
        raise RuntimeError("Fact graph extraction omitted fact ids: " + ", ".join(missing))

    return {"nodes": list(nodes.values()), "edges": edges}


def _store_fact_graph(project: TextProject, graph: dict[str, Any]) -> None:
    state = dict(project.creative_state or {})
    workspace = dict(state.get("agent_workspace") or {})
    workspace["fact_graph"] = graph
    workspace["updated_at"] = datetime.now(timezone.utc).isoformat()
    state["agent_workspace"] = workspace
    project.creative_state = state


def _build_fact_sync_idempotency_key(project_id: str, fact_id: str | None, action: str) -> str:
    payload = {
        "project_id": str(project_id or "").strip(),
        "fact_id": str(fact_id or "").strip(),
        "action": str(action or "").strip().lower(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"fact_memory_sync:{digest}"


async def run_fact_memory_sync_task(
    task_id: str,
    *,
    project_id: str,
    fact_id: str | None = None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading facts and project context...",
        progress_detail={"stage": "setup", "fact_id": fact_id},
    )
    async with async_session() as db:
        try:
            result = await db.execute(
                select(TextProject)
                .where(TextProject.id == project_id)
                .options(
                    selectinload(TextProject.chapters),

                    selectinload(TextProject.facts),
                )
            )
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            facts = [fact for fact in project.facts if fact.memory_status != "deleted"]
            for fact in facts:
                fact.memory_status = "syncing"
                fact.memory_task_id = task_id
                fact.memory_error = None

            ontology_model, agent_model, memory_model, embedding_model = _require_fact_sync_models(project)

            if not facts and not any(chapter_has_memory_material(ch) for ch in sorted_project_chapters(project)):
                task_manager.update_task(task_id, progress=35, message="Deleting empty project memory...", progress_detail={"stage": "memory"})
                await delete_memory(project_id, db=db, embedding_model=embedding_model)
                project.memory_id = None
                _store_fact_graph(project, {"nodes": [], "edges": []})
                write_project_workspace_version_snapshot(
                    project,
                    project.chapters,
                    project.facts,
                    "Clear fact memory",
                )
                await db.commit()
                task_manager.complete_task(task_id, {"memory_id": None, "fact_count": 0}, "Fact memory cleared")
                return

            facts_text = "\n\n".join(_fact_memory_text(fact) for fact in facts)
            memory_text = _compose_project_memory_text(project, facts)
            task_manager.update_task(task_id, progress=22, message="Generating fact ontology...", progress_detail={"stage": "ontology"})
            ontology = await generate_ontology(
                text=facts_text or memory_text,
                db=db,
                requirement="Generate an ontology for project facts. Cover people, objects, events, places, and relationships when present.",
                model=ontology_model,
            )
            project.ontology_schema = ontology

            task_manager.update_task(task_id, progress=42, message="Extracting fact entities and relationships...", progress_detail={"stage": "graph"})
            if facts:
                graph = await _extract_fact_graph(
                    facts=facts,
                    ontology=ontology,
                    model=agent_model,
                    project=project,
                    db=db,
                )
            else:
                graph = {"nodes": [], "edges": []}
            _store_fact_graph(project, graph)

            task_manager.update_task(task_id, progress=68, message="Rebuilding cognee memory from facts...", progress_detail={"stage": "memory"})
            memory_input = build_memory_input_with_ontology(memory_text, ontology)
            memory_id = await build_memory(
                project_id,
                memory_input,
                ontology=ontology,
                db=db,
                model=memory_model,
                embedding_model=embedding_model,
                memory_id_override=project.memory_id or f"memory_{uuid4().hex[:16]}",
                reset=True,
            )
            project.memory_id = memory_id
            # cognee owns graph extraction inside `cognify()`; no separate project_graph step.

            task_manager.update_task(task_id, progress=90, message="Verifying memory graph export...", progress_detail={"stage": "verify"})
            visualization = await get_memory_visualization(project_id, db=db)
            for fact in facts:
                fact.memory_status = "ready"
                fact.memory_task_id = task_id
                fact.memory_error = None
            write_project_workspace_version_snapshot(
                project,
                project.chapters,
                project.facts,
                "Rebuild fact memory",
            )
            await db.commit()
            task_manager.complete_task(
                task_id,
                {
                    "memory_id": memory_id,
                    "fact_id": fact_id,
                    "fact_count": len(facts),
                    "graph_nodes": len(graph.get("nodes") or []),
                    "graph_edges": len(graph.get("edges") or []),
                    "visualization_nodes": len(visualization.get("nodes") or []),
                    "visualization_edges": len(visualization.get("edges") or []),
                },
                "Fact memory synced",
            )
        except asyncio.CancelledError:
            await db.rollback()
            task_manager.update_task(task_id, status=TaskStatus.CANCELLED, message="Fact memory sync cancelled")
            raise
        except Exception as exc:
            await db.rollback()
            async with async_session() as error_db:
                result = await error_db.execute(select(ProjectFact).where(ProjectFact.project_id == project_id))
                for fact in result.scalars().all():
                    if fact_id and fact.id != fact_id:
                        continue
                    fact.memory_status = "failed"
                    fact.memory_task_id = task_id
                    fact.memory_error = str(exc)
                await error_db.commit()
            task_manager.fail_task(task_id, str(exc), "Failed to sync fact memory")


def schedule_fact_memory_sync(
    *,
    project_id: str,
    user_id: str,
    action: str,
    fact_id: str | None = None,
) -> str:
    idempotency_key = _build_fact_sync_idempotency_key(project_id, fact_id, action)
    existing = task_manager.find_inflight_task_by_idempotency(
        task_type=FACT_SYNC_TASK_TYPE,
        project_id=project_id,
        idempotency_key=idempotency_key,
        max_age_minutes=2,
    )
    if existing is not None:
        return existing.task_id

    task = task_manager.create_task(
        FACT_SYNC_TASK_TYPE,
        {
            "project_id": project_id,
            "user_id": user_id,
            "fact_id": str(fact_id or "").strip() or None,
            "action": str(action or "").strip().lower(),
            "auto_created": True,
            "idempotency_key": idempotency_key,
        },
    )

    async def _runner() -> None:
        try:
            await run_fact_memory_sync_task(task.task_id, project_id=project_id, fact_id=fact_id)
        finally:
            task_manager.unregister_runner(task.task_id)

    runner = asyncio.create_task(_runner())
    task_manager.register_runner(task.task_id, runner)
    return task.task_id
