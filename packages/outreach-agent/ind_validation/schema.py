"""Shared IND manifest schema (Mohamed generator ↔ Amine packager contract)."""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

SectionStatus = Literal["present", "omitted", "stub"]
Provenance = Literal["real", "model_derived", "placeholder"]
ValidationStatus = Literal["not_validated", "pending", "passed", "failed"]


class DrugEntry(BaseModel):
    id: str
    is_placeholder: bool = False
    mechanism: str = ""
    hallmark_target: str = ""
    dose: str = ""


class ClaimEntry(BaseModel):
    field: str = ""
    value: Union[str, float, int] = ""
    study_stage: str = ""
    provenance: Provenance = "placeholder"


class IdentifierEntry(BaseModel):
    type: str
    value: str
    provenance: Provenance = "placeholder"


class SectionEntry(BaseModel):
    status: SectionStatus = "present"


class StatisticEntry(BaseModel):
    label: str = ""
    value: str = ""
    study_stage: str = ""
    phase: str = ""


class SignatoryEntry(BaseModel):
    name: str
    verified: bool = False


class HypothesisScore(BaseModel):
    id: str = ""
    acs: float = 0.0


class INDManifest(BaseModel):
    hypothesis_id: str = ""
    disease: str = ""
    phase: str = "1"
    validation_status: ValidationStatus = "not_validated"
    failures: list[str] = Field(default_factory=list)
    public_renderable: bool = False
    drugs: list[DrugEntry] = Field(default_factory=list)
    claims: list[ClaimEntry] = Field(default_factory=list)
    identifiers: list[IdentifierEntry] = Field(default_factory=list)
    sections: dict[str, SectionEntry] = Field(default_factory=dict)
    statistics: list[StatisticEntry] = Field(default_factory=list)
    hallmark_targets: list[str] = Field(default_factory=list)
    aging_coverage_score: float = 0.0
    selected_hypothesis: HypothesisScore = Field(default_factory=HypothesisScore)
    selection_override_rationale: str = ""
    alternatives: list[HypothesisScore] = Field(default_factory=list)
    signatories: list[SignatoryEntry] = Field(default_factory=list)

    @field_validator("phase", mode="before")
    @classmethod
    def _normalize_phase(cls, value: Any) -> str:
        if value is None:
            return "1"
        text = str(value).strip()
        if text.lower().startswith("phase"):
            return text
        return f"Phase {text}" if text.isdigit() else text

    @model_validator(mode="before")
    @classmethod
    def _normalize_sections(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("sections")
        if isinstance(raw, list):
            data = dict(data)
            data["sections"] = {
                str(item.get("id", item.get("section_id", ""))): {"status": item.get("status", "present")}
                for item in raw
                if isinstance(item, dict) and item.get("id", item.get("section_id"))
            }
        # Back-compat alias from earlier drafts
        if "public_disclosure_allowed" in data and "public_renderable" not in data:
            data["public_renderable"] = data["public_disclosure_allowed"]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "INDManifest":
        return cls.model_validate(data)
