from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tomllib
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.config import AIProviderConfig, PaymentConfig
from app.models.project import TextProject
from app.services.graph_service import build_graph, search_graph
from app.services.ontology import build_graph_input_with_ontology, generate_ontology


SAMPLE_TEXT = """
At Lantern Harbor Observatory, engineer Mira Chen and archivist Jonas Vale discovered that the city's tide engine had started failing three nights before the Eclipse Festival.
Mayor Elian Ward asked Mira to inspect the brass regulators, while Captain Imani Ross kept the harbor closed to every cargo ship.
Jonas had secretly exchanged letters with Professor Soren Hale of Northbridge Institute about an ancient survey map hidden beneath the observatory floor.

When the map was opened, it pointed to a maintenance tunnel under Saint Rowan Bridge.
Imani escorted Mira and Jonas into the tunnel, where they found smuggler leader Kade Mercer stealing crystal batteries from the tide engine.
Soren arrived and admitted that he had hired Kade to recover the batteries so he could prove his theory about the city's founder, Ada Rowan.

Mira restored the tide engine before sunrise, Elian reopened the harbor, and Jonas deposited the recovered map in the civic archive.
""".strip()


class _ResultProxy:
    def __init__(self, values: list[Any]):
        self._values = values

    def scalars(self) -> "_ResultProxy":
        return self

    def all(self) -> list[Any]:
        return list(self._values)

    def scalar_one_or_none(self) -> Any | None:
        return self._values[0] if self._values else None


class _FakeAsyncSession:
    def __init__(self, *, provider: Any, payment: Any, project: Any):
        self.provider = provider
        self.payment = payment
        self.project = project

    async def execute(self, statement: Any) -> _ResultProxy:
        entity = None
        try:
            entity = statement.column_descriptions[0].get("entity")
        except Exception:
            entity = None
        if entity is AIProviderConfig:
            return _ResultProxy([self.provider])
        if entity is PaymentConfig:
            return _ResultProxy([self.payment])
        if entity is TextProject:
            return _ResultProxy([self.project])
        raise RuntimeError(f"Unsupported fake query entity: {entity!r}")


def _load_openai_key(auth_path: Path) -> str:
    key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    data = json.loads(auth_path.read_text(encoding="utf-8"))
    key = str(data.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY is missing in {auth_path}")
    return key


def _load_openai_base_url(config_path: Path) -> str:
    base_url = str(os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").strip()
    if base_url:
        return base_url
    if not config_path.exists():
        return "https://api.openai.com/v1"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    provider_name = str(data.get("model_provider") or "").strip()
    providers = data.get("model_providers")
    if not provider_name or not isinstance(providers, dict):
        return "https://api.openai.com/v1"
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return "https://api.openai.com/v1"
    base_url = str(provider.get("base_url") or "").strip()
    return base_url or "https://api.openai.com/v1"


def _build_paths(graph_root: Path, project_id: str) -> tuple[Path, Path]:
    run_root = graph_root / project_id
    return run_root, run_root / "graphiti.kuzu"


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    stage = "setup"
    try:
        api_key = _load_openai_key(Path(args.auth_file).expanduser())
        base_url = _load_openai_base_url(Path(args.codex_config).expanduser())
        project_id = str(args.project_id or uuid.uuid4())
        run_root, graph_path = _build_paths(Path(args.graph_root).expanduser(), project_id)
        run_root.mkdir(parents=True, exist_ok=True)

        settings.GRAPH_BACKEND = "graphiti"
        settings.TELEMETRY_DISABLED = True
        settings.GRAPHITI_DB_PATH = str(graph_path)

        provider = SimpleNamespace(
            id=f"provider-{project_id}",
            name="Codex OpenAI",
            provider="openai_compatible",
            api_key=api_key,
            base_url=base_url,
            models={
                "models": [args.model, args.reranker_model],
                "embedding_models": [args.embedding_model],
                "reranker_models": [args.reranker_model],
            },
            is_active=True,
            priority=100,
        )
        payment = SimpleNamespace(
            id=f"payment-{project_id}",
            name="smoke-runtime",
            type="oasis",
            config={
                "llm_openai_api_style": "responses",
                "llm_prefer_stream": True,
                "llm_stream_fallback_nonstream": True,
                "llm_request_timeout_seconds": 240,
                "llm_retry_count": 2,
                "llm_retry_interval_seconds": 2.0,
                "llm_task_concurrency": 2,
                "llm_model_default_concurrency": 2,
                "llm_reasoning_effort": str(args.reasoning_effort or "").strip() or "model_default",
            },
        )
        project = SimpleNamespace(
            id=project_id,
            user_id="smoke-user",
            title="Graphiti Smoke Project",
            component_models={
                "ontology_generation": args.model,
                "graph_build": args.model,
                "graph_embedding": args.embedding_model,
                "graph_reranker": args.reranker_model,
            },
            ontology_schema=None,
            graph_id=None,
        )
        db = _FakeAsyncSession(provider=provider, payment=payment, project=project)

        stage = "ontology"
        if args.manual_ontology_file:
            ontology_path = Path(args.manual_ontology_file).expanduser()
            ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
        else:
            if args.skip_ontology:
                raise RuntimeError("--skip-ontology requires --manual-ontology-file")
            ontology = await generate_ontology(
                SAMPLE_TEXT,
                db,
                requirement=args.requirement,
                model=args.model,
            )
        if args.dump_ontology_file:
            dump_path = Path(args.dump_ontology_file).expanduser()
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text(json.dumps(ontology, ensure_ascii=False, indent=2), encoding="utf-8")
        project.ontology_schema = ontology

        stage = "build_graph"
        graph_input = build_graph_input_with_ontology(SAMPLE_TEXT, ontology)
        graph_id = await build_graph(
            project_id,
            graph_input,
            ontology=ontology,
            db=db,
            model=args.model,
            embedding_model=args.embedding_model,
        )
        project.graph_id = graph_id

        stage = "search_graph"
        results = await search_graph(
            project_id,
            args.query,
            top_k=args.top_k,
            db=db,
            search_type="INSIGHTS",
        )

        return {
            "project_id": project_id,
            "graph_store": str(graph_path),
            "model": args.model,
            "embedding_model": args.embedding_model,
            "reranker_model": args.reranker_model,
            "base_url": base_url,
            "reasoning_effort": str(args.reasoning_effort or "").strip() or "model_default",
            "ontology_entities": len(ontology.get("entity_types") or []),
            "ontology_edges": len(ontology.get("edge_types") or []),
            "graph_id": graph_id,
            "ontology_source": "manual_file" if args.manual_ontology_file else "generated",
            "query": args.query,
            "search_results": results[: args.top_k],
            "top_result": results[0] if results else None,
        }
    except Exception as exc:
        raise RuntimeError(f"graphiti_smoke_stage_failed:{stage}:{type(exc).__name__}:{exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real Graphiti smoke flow with OpenAI credentials.")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--reranker-model", default="gpt-5.4")
    parser.add_argument("--project-id", default="")
    parser.add_argument(
        "--graph-root",
        default=str(ROOT / ".musegraph" / "smoke"),
    )
    parser.add_argument(
        "--auth-file",
        default=str(Path.home() / ".codex" / "auth.json"),
    )
    parser.add_argument(
        "--codex-config",
        default=str(Path.home() / ".codex" / "config.toml"),
    )
    parser.add_argument(
        "--query",
        default="Who was stealing crystal batteries from the tide engine?",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--requirement",
        default="Focus on people, organizations, locations, artifacts, incidents, and explicit causal relationships.",
    )
    parser.add_argument(
        "--manual-ontology-file",
        default="",
    )
    parser.add_argument(
        "--dump-ontology-file",
        default="",
    )
    parser.add_argument(
        "--skip-ontology",
        action="store_true",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="model_default",
        help="Set runtime llm_reasoning_effort, for example: model_default, none, minimal, low, medium, high, xhigh.",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(_run(args))
    except Exception as exc:
        raise RuntimeError(f"graphiti_smoke_failed:{type(exc).__name__}:{exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
