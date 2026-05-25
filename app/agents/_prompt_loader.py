from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a versioned prompt file, stripping YAML frontmatter."""
    text = (_PROMPTS_DIR / f"{name}.md").read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()
