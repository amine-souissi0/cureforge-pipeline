import re
from typing import Dict

from config.templates import TEMPLATES, TemplateDefinition


class MissingFieldError(ValueError):
    """Raised when a required template field is not provided."""


class TemplateRegistry:
    @staticmethod
    def get(template_id: str) -> TemplateDefinition:
        if template_id not in TEMPLATES:
            raise KeyError(f"Unknown template: {template_id!r}. Valid: {list(TEMPLATES)}")
        return TEMPLATES[template_id]

    @staticmethod
    def render(template_id: str, fields: Dict[str, str]) -> tuple[str, str]:
        """
        Render subject and body for a template with the given fields.

        Returns (subject, body). Raises MissingFieldError if a required
        field is absent or empty.
        """
        tmpl = TemplateRegistry.get(template_id)

        missing = [f for f in tmpl.required_fields if not fields.get(f, "").strip()]
        if missing:
            raise MissingFieldError(f"Missing required fields for {template_id!r}: {missing}")

        subject = _substitute(tmpl.subject_template, fields)
        body = _substitute(tmpl.body_template, fields)
        return subject, body

    @staticmethod
    def list_templates() -> list[str]:
        return list(TEMPLATES.keys())


def _substitute(template: str, fields: Dict[str, str]) -> str:
    """Replace {placeholder} tokens with field values. Unknown placeholders are left as-is."""
    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        key = match.group(1)
        return fields.get(key, match.group(0))

    return re.sub(r"\{(\w+)\}", _replace, template)
