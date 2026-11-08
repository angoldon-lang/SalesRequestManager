"""Ruoli a 3 livelli: ADMIN, BACKOFFICE (ex OPERATOR), SALES + collegamento utente->agente.

Idempotente: sulle installazioni nuove lo schema (0001) contiene già lo stato finale.
"""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                     WHERE t.typname = 'user_role' AND e.enumlabel = 'OPERATOR') THEN
            ALTER TYPE user_role RENAME VALUE 'OPERATOR' TO 'BACKOFFICE';
          END IF;
        END $$;""")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'SALES'")
    op.execute("""ALTER TABLE app_users ADD COLUMN IF NOT EXISTS sales_agent_id BIGINT
                  UNIQUE REFERENCES sales_agents(id) ON DELETE SET NULL""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_requests_agent ON requests(sales_agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_requests_creator ON requests(created_by)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_requests_agent, ix_requests_creator")
    op.execute("ALTER TABLE app_users DROP COLUMN IF EXISTS sales_agent_id")
