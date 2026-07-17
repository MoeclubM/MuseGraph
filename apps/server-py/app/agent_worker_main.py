import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app.config import settings
from app.database import async_session
from app.models.runtime import AgentRun
from app.services.agent_engine import append_agent_event, execute_agent_run
from app.services.agent_workspace import delete_run_workspace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("musegraph.agent-worker")


def worker_id() -> str:
    return settings.AGENT_WORKER_ID or f"{socket.gethostname()}:{os.getpid()}"


async def claim_run(identity: str) -> str | None:
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        async with db.begin():
            result = await db.execute(
                select(AgentRun)
                .where(
                    or_(
                        AgentRun.status == "queued",
                        (
                            (AgentRun.status == "running")
                            & (AgentRun.lease_expires_at < now)
                        ),
                    )
                )
                .order_by(AgentRun.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            run = result.scalar_one_or_none()
            if run is None:
                return None
            run.status = "running"
            run.lease_owner = identity
            run.lease_expires_at = now + timedelta(seconds=settings.AGENT_WORKER_LEASE_SECONDS)
            run.heartbeat_at = now
            run.started_at = run.started_at or now
            run.error = None
            run_id = run.id
    await append_agent_event(run_id, "running", {"worker": identity})
    return run_id


async def maintain_lease(run_id: str, identity: str) -> None:
    interval = max(1, settings.AGENT_WORKER_LEASE_SECONDS // 3)
    while True:
        await asyncio.sleep(interval)
        now = datetime.now(timezone.utc)
        async with async_session() as db:
            state = (
                await db.execute(
                    select(
                        AgentRun.status,
                        AgentRun.lease_owner,
                        AgentRun.cancel_requested,
                    ).where(AgentRun.id == run_id)
                )
            ).one()
            if state.cancel_requested:
                raise InterruptedError("Agent run cancellation requested")
            if state.status != "running":
                return
            if state.lease_owner != identity:
                raise RuntimeError(f"Worker lease was lost for Agent run {run_id}")
            result = await db.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.status == "running",
                    AgentRun.lease_owner == identity,
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now
                    + timedelta(seconds=settings.AGENT_WORKER_LEASE_SECONDS),
                )
            )
            await db.commit()
        if result.rowcount != 1:
            async with async_session() as db:
                status_result = await db.execute(
                    select(AgentRun.status).where(AgentRun.id == run_id)
                )
                status = status_result.scalar_one()
            if status != "running":
                return
            raise RuntimeError(f"Worker lease was lost for Agent run {run_id}")


async def execute_claimed_run(run_id: str, identity: str) -> None:
    execution = asyncio.create_task(execute_agent_run(run_id, identity))
    heartbeat = asyncio.create_task(maintain_lease(run_id, identity))
    done, _ = await asyncio.wait(
        {execution, heartbeat},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if heartbeat in done:
        if heartbeat.exception() is not None:
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            if isinstance(heartbeat.exception(), InterruptedError):
                async with async_session() as db:
                    run = (
                        await db.execute(
                            select(AgentRun).where(AgentRun.id == run_id)
                        )
                    ).scalar_one()
                    run.status = "cancelled"
                    run.completed_at = datetime.now(timezone.utc)
                    run.lease_owner = None
                    run.lease_expires_at = None
                    await db.commit()
                delete_run_workspace(run_id)
                await append_agent_event(
                    run_id,
                    "cancelled",
                    {"message": "Agent run cancelled"},
                )
                return
            heartbeat.result()
        await execution
        return
    heartbeat.cancel()
    await asyncio.gather(heartbeat, return_exceptions=True)
    await execution


async def main() -> None:
    identity = worker_id()
    logger.info("Agent worker started: %s", identity)
    while True:
        run_id = await claim_run(identity)
        if run_id is None:
            await asyncio.sleep(1)
            continue
        try:
            await execute_claimed_run(run_id, identity)
        except Exception:
            logger.exception("Agent run failed: %s", run_id)


if __name__ == "__main__":
    asyncio.run(main())
