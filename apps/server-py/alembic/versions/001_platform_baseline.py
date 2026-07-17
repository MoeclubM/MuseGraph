"""MuseGraph platform baseline.

Revision ID: 001_platform_baseline
Revises:
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001_platform_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CREATE_STATEMENTS = (
    """
    CREATE TABLE ai_provider_configs (
        id UUID PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        provider VARCHAR(50) NOT NULL,
        api_key VARCHAR(500) NOT NULL,
        base_url VARCHAR(500),
        models JSON,
        embedding_models JSON,
        reranker_models JSON,
        is_active BOOLEAN NOT NULL,
        priority INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE payment_adapters (
        id UUID PRIMARY KEY,
        adapter_type VARCHAR(50) NOT NULL,
        display_name VARCHAR(100) NOT NULL,
        config JSON,
        enabled BOOLEAN NOT NULL,
        sort_order INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE payment_configs (
        id UUID PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        type VARCHAR(50) NOT NULL,
        config JSON,
        is_active BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE pricing_rules (
        id UUID PRIMARY KEY,
        model VARCHAR(100) NOT NULL UNIQUE,
        billing_mode VARCHAR(20) NOT NULL,
        input_price NUMERIC(10, 6) NOT NULL,
        output_price NUMERIC(10, 6) NOT NULL,
        token_unit INTEGER NOT NULL,
        request_price NUMERIC(10, 6) NOT NULL,
        is_active BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE users (
        id UUID PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        nickname VARCHAR(100),
        avatar VARCHAR(500),
        balance NUMERIC(12, 6) NOT NULL,
        is_admin BOOLEAN NOT NULL,
        status VARCHAR(20) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_users_status
            CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'))
    )
    """,
    """
    CREATE TABLE deposits (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        amount NUMERIC(10, 4) NOT NULL,
        status VARCHAR(20) NOT NULL,
        payment_method VARCHAR(50),
        payment_id VARCHAR(255) UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        processed_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE orders (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        order_no VARCHAR(100) NOT NULL UNIQUE,
        type VARCHAR(20) NOT NULL,
        amount NUMERIC(10, 4) NOT NULL,
        status VARCHAR(20) NOT NULL,
        payment_adapter_id UUID REFERENCES payment_adapters(id) ON DELETE SET NULL,
        payment_method VARCHAR(50),
        payment_id VARCHAR(255),
        paid_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE sessions (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        csrf_token_hash VARCHAR(64) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE text_projects (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        visibility VARCHAR(20) NOT NULL,
        component_models JSON NOT NULL,
        active_revision_id UUID,
        memory_instance_id VARCHAR(255) NOT NULL UNIQUE,
        pack_slug VARCHAR(64) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_text_projects_visibility
            CHECK (visibility IN ('private', 'public'))
    )
    """,
    """
    CREATE TABLE audit_logs (
        id UUID PRIMARY KEY,
        actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        project_id UUID REFERENCES text_projects(id) ON DELETE SET NULL,
        action VARCHAR(120) NOT NULL,
        target_type VARCHAR(80) NOT NULL,
        target_id VARCHAR(128),
        request_id VARCHAR(64),
        ip_address VARCHAR(64),
        detail JSON NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE document_index (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES text_projects(id) ON DELETE CASCADE,
        path VARCHAR(1024) NOT NULL,
        title VARCHAR(255) NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        git_commit VARCHAR(64) NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_document_index_project_path UNIQUE (project_id, path)
    )
    """,
    """
    CREATE TABLE project_members (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES text_projects(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_project_members_role
            CHECK (role IN ('owner', 'editor', 'viewer')),
        CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id)
    )
    """,
    """
    CREATE TABLE project_revisions (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES text_projects(id) ON DELETE CASCADE,
        parent_revision_id UUID REFERENCES project_revisions(id) ON DELETE SET NULL,
        git_commit VARCHAR(64) NOT NULL,
        knowledge_dataset VARCHAR(255) NOT NULL,
        created_by_run_id VARCHAR(64),
        status VARCHAR(20) NOT NULL,
        message VARCHAR(500) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_project_revisions_status
            CHECK (status IN ('active', 'superseded'))
    )
    """,
    """
    CREATE TABLE project_skills (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES text_projects(id) ON DELETE CASCADE,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(120) NOT NULL,
        description TEXT NOT NULL,
        instructions TEXT NOT NULL,
        scopes JSON NOT NULL,
        roles JSON NOT NULL,
        allowed_tools JSON NOT NULL,
        params_schema JSON NOT NULL,
        default_model_component VARCHAR(80),
        version INTEGER NOT NULL,
        enabled BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_project_skills_project_slug UNIQUE (project_id, slug)
    )
    """,
    """
    CREATE TABLE agent_runs (
        id VARCHAR(64) PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES text_projects(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        base_revision_id UUID REFERENCES project_revisions(id) ON DELETE SET NULL,
        result_revision_id UUID REFERENCES project_revisions(id) ON DELETE SET NULL,
        mode VARCHAR(20) NOT NULL,
        status VARCHAR(24) NOT NULL,
        instruction TEXT NOT NULL,
        model VARCHAR(160),
        effort VARCHAR(20),
        target_refs JSON NOT NULL,
        plan JSON,
        context_snapshot JSON,
        skill_snapshot JSON NOT NULL,
        change_set JSON NOT NULL,
        final_output JSON,
        self_review JSON,
        validation JSON,
        error TEXT,
        cancel_requested BOOLEAN NOT NULL,
        lease_owner VARCHAR(128),
        lease_expires_at TIMESTAMPTZ,
        heartbeat_at TIMESTAMPTZ,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_agent_runs_mode CHECK (mode IN ('write', 'analyze', 'suggest')),
        CONSTRAINT ck_agent_runs_status CHECK (
            status IN (
                'queued', 'running', 'awaiting_review', 'accepting', 'completed',
                'rejected', 'conflicted', 'failed', 'cancelled'
            )
        )
    )
    """,
    """
    CREATE TABLE agent_events (
        id UUID PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        data JSON NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_events_run_sequence UNIQUE (run_id, sequence)
    )
    """,
    """
    CREATE TABLE usages (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id UUID REFERENCES text_projects(id) ON DELETE SET NULL,
        operation_id VARCHAR(64) REFERENCES agent_runs(id) ON DELETE SET NULL,
        model VARCHAR(100),
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        cost NUMERIC(10, 6) NOT NULL,
        provider VARCHAR(100),
        billing_mode VARCHAR(20),
        request_id VARCHAR(128),
        status VARCHAR(32) NOT NULL,
        source VARCHAR(32) NOT NULL,
        metadata JSON,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_sessions_user_id ON sessions (user_id)",
    "CREATE INDEX ix_text_projects_user_id ON text_projects (user_id)",
    "CREATE INDEX ix_text_projects_visibility_updated ON text_projects (visibility, updated_at)",
    "CREATE INDEX ix_audit_logs_project_created ON audit_logs (project_id, created_at)",
    "CREATE INDEX ix_audit_logs_actor_created ON audit_logs (actor_user_id, created_at)",
    "CREATE INDEX ix_document_index_project_commit ON document_index (project_id, git_commit)",
    "CREATE INDEX ix_project_members_user_id ON project_members (user_id)",
    "CREATE INDEX ix_project_members_project_id ON project_members (project_id)",
    "CREATE INDEX ix_project_revisions_project_created ON project_revisions (project_id, created_at)",
    """
    CREATE UNIQUE INDEX uq_project_revisions_one_active
        ON project_revisions (project_id) WHERE status = 'active'
    """,
    "CREATE INDEX ix_project_skills_project_enabled ON project_skills (project_id, enabled)",
    "CREATE INDEX ix_agent_runs_queue ON agent_runs (status, created_at)",
    "CREATE INDEX ix_agent_runs_project_created ON agent_runs (project_id, created_at)",
    "CREATE INDEX ix_agent_runs_lease ON agent_runs (status, lease_expires_at)",
    "CREATE INDEX ix_agent_events_run_sequence ON agent_events (run_id, sequence)",
    """
    ALTER TABLE text_projects
        ADD CONSTRAINT fk_text_projects_active_revision
        FOREIGN KEY (active_revision_id)
        REFERENCES project_revisions(id)
        ON DELETE SET NULL
    """,
)


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE text_projects DROP CONSTRAINT fk_text_projects_active_revision"
    )
    for table in (
        "usages",
        "agent_events",
        "agent_runs",
        "project_skills",
        "project_revisions",
        "project_members",
        "document_index",
        "audit_logs",
        "text_projects",
        "sessions",
        "orders",
        "deposits",
        "users",
        "pricing_rules",
        "payment_configs",
        "payment_adapters",
        "ai_provider_configs",
    ):
        op.execute(f'DROP TABLE "{table}"')
