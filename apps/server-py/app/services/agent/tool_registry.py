from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.runtime import KnowledgeDelete, KnowledgeRecord, KnowledgeUpsert
from app.services.agent_workspace import (
    delete_run_file,
    list_run_files,
    read_run_file,
    write_run_file,
)
from app.services.memory_client import recall_knowledge


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(ToolInput):
    pass


class ReadFileInput(ToolInput):
    path: str = Field(min_length=1, max_length=1024)


class WriteFileInput(ToolInput):
    path: str = Field(min_length=1, max_length=1024)
    content: str


class DeleteFileInput(ToolInput):
    path: str = Field(min_length=1, max_length=1024)


class KnowledgeSearchInput(ToolInput):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class KnowledgeGetInput(ToolInput):
    record_id: str = Field(min_length=1, max_length=128)


class KnowledgeUpsertInput(ToolInput):
    record: KnowledgeRecord


class KnowledgeDeleteInput(ToolInput):
    record_id: str = Field(min_length=1, max_length=128)


@dataclass
class ToolContext:
    project_id: str
    run_id: str
    role: str
    dataset_name: str
    knowledge_records: dict[str, dict[str, Any]]
    knowledge_operations: list[KnowledgeUpsert | KnowledgeDelete]


ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    roles: frozenset[str]
    mutation: Literal["read", "file", "knowledge"]

    def json_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema(),
        }


async def _list_files(context: ToolContext, body: EmptyInput) -> Any:
    return {"files": list_run_files(context.run_id)}


async def _read_file(context: ToolContext, body: ReadFileInput) -> Any:
    return {"path": body.path, "content": read_run_file(context.run_id, body.path)}


async def _write_file(context: ToolContext, body: WriteFileInput) -> Any:
    return write_run_file(context.run_id, body.path, body.content)


async def _delete_file(context: ToolContext, body: DeleteFileInput) -> Any:
    delete_run_file(context.run_id, body.path)
    return {"path": body.path, "deleted": True}


async def _knowledge_search(context: ToolContext, body: KnowledgeSearchInput) -> Any:
    semantic = (
        await recall_knowledge(
            context.project_id,
            context.dataset_name,
            body.query,
            top_k=body.top_k,
        )
        if context.knowledge_records
        else []
    )
    query = body.query.casefold()
    exact = [
        record
        for record in context.knowledge_records.values()
        if query in str(record.get("title") or "").casefold()
        or query in str(record.get("content") or "").casefold()
    ][: body.top_k]
    return {"records": exact, "semantic_context": semantic}


async def _knowledge_get(context: ToolContext, body: KnowledgeGetInput) -> Any:
    record = context.knowledge_records.get(body.record_id)
    if record is None:
        raise LookupError(f"Knowledge record not found: {body.record_id}")
    return {"record": record}


async def _knowledge_upsert(context: ToolContext, body: KnowledgeUpsertInput) -> Any:
    record = body.record.model_dump(mode="json")
    context.knowledge_records[record["id"]] = record
    context.knowledge_operations.append(KnowledgeUpsert(record=body.record))
    return {"record": record}


async def _knowledge_delete(context: ToolContext, body: KnowledgeDeleteInput) -> Any:
    if body.record_id not in context.knowledge_records:
        raise LookupError(f"Knowledge record not found: {body.record_id}")
    del context.knowledge_records[body.record_id]
    context.knowledge_operations.append(KnowledgeDelete(record_id=body.record_id))
    return {"record_id": body.record_id, "deleted": True}


READ_ROLES = frozenset(
    {
        "planner",
        "composer",
        "writer",
        "auditor",
        "reviser",
        "evaluator",
        "updater",
        "memory_builder",
        "graph_extractor",
    }
)
FILE_WRITE_ROLES = frozenset({"writer", "reviser"})
KNOWLEDGE_WRITE_ROLES = frozenset({"updater", "memory_builder", "graph_extractor"})

TOOL_REGISTRY: dict[str, ToolDefinition] = {
    definition.name: definition
    for definition in (
        ToolDefinition("list_files", "列出会话工作区文件。", EmptyInput, _list_files, READ_ROLES, "read"),
        ToolDefinition("read_file", "读取会话工作区 UTF-8 文本文件。", ReadFileInput, _read_file, READ_ROLES, "read"),
        ToolDefinition("write_file", "写入会话工作区文本文件。", WriteFileInput, _write_file, FILE_WRITE_ROLES, "file"),
        ToolDefinition("delete_file", "删除会话工作区文本文件。", DeleteFileInput, _delete_file, FILE_WRITE_ROLES, "file"),
        ToolDefinition(
            "knowledge_search",
            "检索当前知识版本和候选知识变更。",
            KnowledgeSearchInput,
            _knowledge_search,
            READ_ROLES,
            "read",
        ),
        ToolDefinition(
            "knowledge_get",
            "按稳定 ID 读取结构化知识。",
            KnowledgeGetInput,
            _knowledge_get,
            READ_ROLES,
            "read",
        ),
        ToolDefinition(
            "knowledge_upsert",
            "新增或替换有来源的严格类型知识记录。",
            KnowledgeUpsertInput,
            _knowledge_upsert,
            KNOWLEDGE_WRITE_ROLES,
            "knowledge",
        ),
        ToolDefinition(
            "knowledge_delete",
            "删除当前知识记录。",
            KnowledgeDeleteInput,
            _knowledge_delete,
            KNOWLEDGE_WRITE_ROLES,
            "knowledge",
        ),
    )
}


def tool_schemas(allowed_tools: set[str], role: str) -> list[dict[str, Any]]:
    return [
        definition.json_schema()
        for name, definition in TOOL_REGISTRY.items()
        if name in allowed_tools and role in definition.roles
    ]


async def execute_tool(
    context: ToolContext,
    tool_name: str,
    arguments: dict[str, Any],
    allowed_tools: set[str],
) -> Any:
    definition = TOOL_REGISTRY.get(tool_name)
    if definition is None:
        raise LookupError(f"Unknown tool: {tool_name}")
    if tool_name not in allowed_tools:
        raise PermissionError(f"Skill does not allow tool: {tool_name}")
    if context.role not in definition.roles:
        raise PermissionError(f"Role {context.role} cannot use tool: {tool_name}")
    body = definition.input_model.model_validate(arguments)
    return await definition.handler(context, body)
