"""Schema iniziale (db/schema.sql) + riga di configurazione di default."""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA.read_text())
    op.execute(
        "INSERT INTO global_config (sender_email, inbound_mailbox, default_cc) "
        "VALUES ('richieste@azienda.it', 'srm-inbound@azienda.it', '{}')"
    )


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS request_events, requests, inbound_emails, global_config, "
        "vendor_supplier_map, suppliers, vendors, sales_agents, app_users CASCADE; "
        "DROP SEQUENCE IF EXISTS request_code_seq; "
        "DROP FUNCTION IF EXISTS set_updated_at(); "
        "DROP TYPE IF EXISTS request_type, request_status, close_reason, request_source, "
        "user_role, inbound_status;"
    )
