from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres@/srm?host=/var/tmp/srmpg"

    # --- Auth (Microsoft Entra ID) ---
    auth_disabled: bool = False          # SOLO sviluppo: nessun login, utente admin fittizio
    az_tenant_id: str = ""
    az_client_id: str = ""               # client id dell'app (stesso usato come audience delle API)
    az_client_secret: str = ""           # usato da Graph (client credentials)
    api_audience: str = ""               # default: az_client_id
    admin_emails: str = ""               # lista separata da virgola: diventano ADMIN al primo login

    # --- Graph ---
    graph_mode: str = "dry-run"          # "graph" (reale) | "dry-run" (log, nessun invio)

    # --- LLM ---
    anthropic_api_key: str = ""
    llm_mode: str = "anthropic"          # "anthropic" | "disabled"

    cors_origins: str = "http://localhost:5173"
    run_workers_in_api: bool = False

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


settings = Settings()
