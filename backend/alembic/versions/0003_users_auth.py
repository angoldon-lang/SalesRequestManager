"""Utenti con autenticazione locale; gli agenti commerciali diventano utenti SALES.

Idempotente: sulle installazioni nuove lo schema (0001) contiene già lo stato finale.
- app_users: username (login), email opzionale, password_hash, cambio password obbligatorio, blocco account
- sales_agents -> app_users (ruolo SALES), requests.sales_agent_id ora punta a app_users
"""
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS username CITEXT;
    UPDATE app_users SET username = email WHERE username IS NULL;
    ALTER TABLE app_users ALTER COLUMN username SET NOT NULL;
    ALTER TABLE app_users ALTER COLUMN email DROP NOT NULL;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS password_hash TEXT;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS failed_logins SMALLINT NOT NULL DEFAULT 0;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
    ALTER TABLE app_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
    ALTER TABLE global_config ADD COLUMN IF NOT EXISTS jwt_secret TEXT;

    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_users_username_key') THEN
        ALTER TABLE app_users ADD CONSTRAINT app_users_username_key UNIQUE (username);
      END IF;
    END $$;

    -- Gli agenti diventano utenti SALES (senza password: l'admin la imposta dalla pagina Utenti)
    DO $$ BEGIN
      IF to_regclass('public.sales_agents') IS NOT NULL THEN
        INSERT INTO app_users (username, email, full_name, role, is_active)
          SELECT a.email, a.email, a.full_name, 'SALES', a.is_active FROM sales_agents a
          ON CONFLICT DO NOTHING;
        ALTER TABLE requests DROP CONSTRAINT IF EXISTS requests_sales_agent_id_fkey;
        UPDATE requests r SET sales_agent_id = u.id
          FROM sales_agents a JOIN app_users u ON u.email = a.email
          WHERE r.sales_agent_id = a.id;
        ALTER TABLE requests ADD CONSTRAINT requests_sales_agent_id_fkey
          FOREIGN KEY (sales_agent_id) REFERENCES app_users(id);
        ALTER TABLE app_users DROP COLUMN IF EXISTS sales_agent_id;
        DROP TABLE sales_agents;
      END IF;
    END $$;

    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_sales_has_email') THEN
        ALTER TABLE app_users ADD CONSTRAINT chk_sales_has_email CHECK (role <> 'SALES' OR email IS NOT NULL);
      END IF;
    END $$;
    """)


def downgrade() -> None:
    raise NotImplementedError("Migrazione non reversibile: ripristina da backup (scripts/restore.sh)")
