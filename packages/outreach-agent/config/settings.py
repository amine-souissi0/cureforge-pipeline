from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── MVP ───────────────────────────────────────────────────────────────────
    resend_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    webhook_secret: str = ""
    webhook_api_key: str = ""
    use_json_logging: bool = False
    db_url: str = "sqlite:///./outreach.db"
    from_email: str = "outreach@longevityintime.org"
    reply_to_email: str = ""
    openai_model: str = "gpt-4o"
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Inbound reply scanner (optional IMAP alternative to Resend webhook) ────
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"

    # ── Preprint / arXiv ─────────────────────────────────────────────────────
    arxiv_username: str = ""
    arxiv_password: str = ""

    # ── USPTO (patent prior art) ─────────────────────────────────────────────
    uspto_api_key: str = ""

    # ── FDA ESG NextGen ──────────────────────────────────────────────────────
    fda_client_id: str = ""
    fda_client_secret: str = ""

    # ── LLM / NVIDIA NIM (patient sim + optional agents) ─────────────────────
    nvidia_api_key: str = ""
    llm_provider: str = ""

    # ── ClickUp ──────────────────────────────────────────────────────────────
    clickup_api_key: str = ""

    # ── Runtime ──────────────────────────────────────────────────────────────
    local_dev: bool = False

    # ── Patent agent (gated output — avoid prior-art exposure) ───────────────
    patent_output_dir: str = "output/patents"


settings = Settings()
