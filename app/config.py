import os


def get_api_key() -> str:
    """
    Load the pipeline API key used to authenticate all protected endpoints.
    Production: replace with boto3 Secrets Manager call.
    """
    key = os.environ.get("API_KEY", "")
    if not key:
        raise RuntimeError("API_KEY environment variable not set")
    return key


def get_anthropic_api_key() -> str:
    """
    Load the Anthropic API key.
    Not required when OLLAMA_BASE_URL is set (local Ollama mode).
    Production: replace with boto3 Secrets Manager call.
    """
    if os.environ.get("OLLAMA_BASE_URL"):
        return ""  # Ollama mode — key unused
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Set OLLAMA_BASE_URL for local Ollama mode."
        )
    return key


GOOGLE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE", "config/google_credentials.json"
)
GOOGLE_TOKEN_FILE = os.environ.get(
    "GOOGLE_TOKEN_FILE", "config/google_token.json"
)
GMAIL_OAUTH_REDIRECT_URI = os.environ.get(
    "GMAIL_OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback"
)
GMAIL_PUBSUB_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_ORG = os.environ.get("GITHUB_ORG", "cureforge-sandbox")
GITHUB_API_URL = "https://api.github.com"


def get_github_token() -> str:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN environment variable not set")
    return GITHUB_TOKEN
