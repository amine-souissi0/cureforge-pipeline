from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    groq_model: str = Field("llama-3.3-70b-versatile", env="GROQ_MODEL")

    # Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_user_id: str = Field(..., env="TELEGRAM_USER_ID")
    telegram_channel: str = Field("UkhvatNews", env="TELEGRAM_CHANNEL")

    # ClickUp
    clickup_api_token: str = Field(..., env="CLICKUP_API_TOKEN")
    clickup_workspace_id: str = Field(..., env="CLICKUP_WORKSPACE_ID")
    clickup_space_id: str = Field(..., env="CLICKUP_SPACE_ID")
    clickup_list_developers: str = Field(..., env="CLICKUP_LIST_DEVELOPERS")
    clickup_list_sales: str = Field(..., env="CLICKUP_LIST_SALES")
    clickup_list_other: str = Field(..., env="CLICKUP_LIST_OTHER")

    # App
    poll_interval: int = Field(300, env="POLL_INTERVAL")
    lookback_hours: int = Field(24, env="LOOKBACK_HOURS")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
