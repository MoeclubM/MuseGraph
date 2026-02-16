from typing import Any

from app.config import settings

# Lazy-loaded SearchType mapping — built once on first use
_SEARCH_TYPE_MAP: dict[str, Any] | None = None


def _get_search_type_map() -> dict[str, Any]:
    global _SEARCH_TYPE_MAP
    if _SEARCH_TYPE_MAP is None:
        from cognee.api.v1.search import SearchType

        _SEARCH_TYPE_MAP = {
            "INSIGHTS": SearchType.INSIGHTS,
            "SUMMARIES": SearchType.SUMMARIES,
            "CHUNKS": SearchType.CHUNKS,
            "GRAPH_COMPLETION": SearchType.GRAPH_COMPLETION,
            "RAG_COMPLETION": SearchType.RAG_COMPLETION,
            "GRAPH_SUMMARY_COMPLETION": SearchType.GRAPH_SUMMARY_COMPLETION,
        }
    return _SEARCH_TYPE_MAP


async def setup_cognee():
    """Configure Cognee with Neo4j, LLM, and embedding settings."""
    try:
        import cognee

        llm_api_key = settings.COGNEE_LLM_API_KEY or settings.OPENAI_API_KEY

        # Patch tiktoken to handle unknown models (e.g. Qwen3-Embedding-0.6B)
        try:
            import tiktoken
            _orig_encoding_for_model = tiktoken.encoding_for_model

            def _patched_encoding_for_model(model_name: str):
                try:
                    return _orig_encoding_for_model(model_name)
                except KeyError:
                    return tiktoken.get_encoding("cl100k_base")

            tiktoken.encoding_for_model = _patched_encoding_for_model
        except Exception:
            pass

        # Patch litellm.aembedding to strip dimensions for custom models
        # (litellm raises UnsupportedParamsError before drop_params can help)
        try:
            import litellm
            _orig_aembedding = litellm.aembedding

            async def _patched_aembedding(*args, **kwargs):
                kwargs.pop("dimensions", None)
                return await _orig_aembedding(*args, **kwargs)

            litellm.aembedding = _patched_aembedding
        except Exception:
            pass

        llm_config: dict = {"llm_api_key": llm_api_key}
        if settings.COGNEE_LLM_MODEL:
            llm_config["llm_model"] = settings.COGNEE_LLM_MODEL
        if settings.COGNEE_LLM_BASE_URL:
            llm_config["llm_endpoint"] = settings.COGNEE_LLM_BASE_URL
        cognee.config.set_llm_config(llm_config)
        cognee.config.set_graph_db_config({
            "graph_database_provider": "neo4j",
            "graph_database_url": settings.NEO4J_URL,
            "graph_database_username": settings.NEO4J_USERNAME,
            "graph_database_password": settings.NEO4J_PASSWORD,
        })

        # Ensure Cognee's internal SQLite database exists (survives container rebuilds)
        try:
            from cognee.infrastructure.databases.relational import get_relational_engine
            engine = get_relational_engine()
            await engine.create_database()
        except Exception:
            pass
    except ImportError:
        pass  # Cognee not installed


async def add_and_cognify(project_id: str, text: str) -> str:
    """Add text to a Cognee dataset, build knowledge graph, and enrich with memify."""
    import cognee

    dataset_name = f"project-{project_id}"
    await cognee.add(text, dataset_name=dataset_name)
    await cognee.cognify(datasets=[dataset_name])
    # Enrich graph with derived facts and memory algorithms
    try:
        await cognee.memify()
    except Exception:
        pass  # memify is optional enrichment; don't fail the whole operation
    return dataset_name


def _parse_result(r: Any) -> dict[str, Any]:
    """Extract content from a single Cognee search result."""
    # Pydantic model / dataclass
    for attr in ("text", "content", "summary"):
        try:
            val = getattr(r, attr, None)
            if val and isinstance(val, str):
                return {"content": val}
        except Exception:
            pass
    # dict
    if isinstance(r, dict):
        text = r.get("text") or r.get("content") or r.get("summary")
        if text:
            return {"content": text}
    # model_dump fallback
    try:
        d = r.model_dump() if hasattr(r, "model_dump") else r.__dict__
        text = d.get("text") or d.get("content") or d.get("summary") or str(r)
        return {"content": text}
    except Exception:
        return {"content": str(r)}


async def search_graph(
    project_id: str,
    query: str,
    search_type: str = "INSIGHTS",
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Search the knowledge graph using Cognee's native search."""
    import cognee

    type_map = _get_search_type_map()
    cognee_type = type_map.get(search_type)
    if cognee_type is None:
        cognee_type = type_map["GRAPH_COMPLETION"]

    results = await cognee.search(
        query_text=query,
        query_type=cognee_type,
        top_k=top_k,
    )

    if not isinstance(results, list):
        return [{"content": str(results), "score": 1.0}]

    parsed = []
    for r in results:
        item = _parse_result(r)
        item.setdefault("score", 1.0)
        parsed.append(item)
    return parsed


async def get_graph_visualization(project_id: str) -> dict[str, Any]:
    """Get graph data for visualization via Cognee's graph engine."""
    try:
        from cognee.infrastructure.databases.graph import get_graph_engine

        graph_engine = await get_graph_engine()
        graph_data = await graph_engine.get_graph_data()

        nodes: list[dict] = []
        edges: list[dict] = []

        if not isinstance(graph_data, tuple) or len(graph_data) != 2:
            return {"nodes": nodes, "edges": edges}

        raw_nodes, raw_edges = graph_data

        for n in raw_nodes:
            if isinstance(n, tuple) and len(n) >= 2:
                node_id = n[0]
                props = n[1] if isinstance(n[1], dict) else {}
            elif isinstance(n, dict):
                node_id = n.get("id", "")
                props = n
            else:
                continue
            label = (
                props.get("name")
                or (props.get("text", "") or "")[:60]
                or str(node_id)[:12]
            )
            nodes.append({
                "id": str(node_id),
                "label": label,
                "type": props.get("type", "CONCEPT"),
            })

        for e in raw_edges:
            if isinstance(e, tuple) and len(e) >= 3:
                props = e[3] if len(e) > 3 and isinstance(e[3], dict) else {}
                edges.append({
                    "source": str(e[0]),
                    "target": str(e[1]),
                    "label": props.get("relationship_name", e[2]),
                })
            elif isinstance(e, dict):
                edges.append({
                    "source": e.get("source", ""),
                    "target": e.get("target", ""),
                    "label": e.get("relationship_name", "RELATED_TO"),
                })

        return {"nodes": nodes, "edges": edges}
    except Exception:
        return {"nodes": [], "edges": []}


async def delete_dataset(project_id: str) -> None:
    """Delete a Cognee dataset using prune API."""
    import cognee

    dataset_name = f"project-{project_id}"
    await cognee.prune.prune_data(dataset_name)
