"""Tests for IND pre-ingestion validation gate (ClickUp 86exujvxw)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ind_validation.gate import validate_ind

FIXTURES = Path(__file__).parent / "fixtures"
IND3_MANIFEST = FIXTURES / "ind_alzheimer_20260523_manifest.json"
IND3_PROSE = Path(__file__).resolve().parents[2] / ".input/clickup_86exujvxw/IND_3.md"

SAMPLE_MANIFEST = {
    "hypothesis_id": "cee29462-e59e-49a7-9be8-893ccbe32605",
    "disease": "alzheimer",
    "phase": "1",
    "drugs": [
        {"id": "drug_1", "is_placeholder": True, "mechanism": "LOXL2 inhibitor"},
        {"id": "drug_2", "is_placeholder": True, "mechanism": "HSF1 activator"},
        {"id": "drug_3", "is_placeholder": True, "mechanism": "IL-6R antagonist"},
    ],
    "identifiers": [
        {"type": "NCT", "value": "NCT05606341", "provenance": "placeholder"},
    ],
    "sections": {"2.2": {"status": "present"}},
    "statistics": [
        {"label": "efficacy", "value": "p=0.0042", "study_stage": "completed Phase 2"},
    ],
    "hallmark_targets": [],
    "aging_coverage_score": 0.0,
    "selected_hypothesis": {"id": "cee29462", "acs": 0.0},
    "alternatives": [{"id": "alt1", "acs": 0.3889}],
    "signatories": [{"name": "Dr. Elena M. Rossi", "verified": False}],
}

SAMPLE_PROSE = """
## 2.2 Summary of Prior Human Experience
Prior trial NCT05606341 enrolled 212 participants.
drug_1 was studied in Phase 2 with adverse events reported.
Alzheimer's Res Ther 2024;12:45.

Sincerely,
Dr. Elena M. Rossi, VP Regulatory Affairs

The regimen provides hallmark coverage across multiple aging pathways.
"""


class TestINDValidationGate:
    def test_fabricated_ind_fails_with_expected_rules(self):
        result = validate_ind(SAMPLE_MANIFEST, SAMPLE_PROSE)
        assert result["validation_status"] == "failed"
        codes = {f.split(":", 1)[0] for f in result["failures"]}
        assert "G1" in codes
        assert "G2" in codes
        assert "G4" in codes
        assert "G5" in codes
        assert "G6" in codes
        assert "G7" in codes

    def test_clean_manifest_passes(self):
        clean = {
            "hypothesis_id": "test-pass-001",
            "disease": "alzheimer",
            "phase": "1",
            "identifiers": [],
            "statistics": [],
            "claims": [],
            "signatories": [],
            "alternatives": [],
            "selected_hypothesis": {"id": "h1", "acs": 0.5},
            "hallmark_targets": ["ECM_stiffening"],
            "aging_coverage_score": 0.4,
            "sections": {"1.0": {"status": "present"}},
            "drugs": [
                {
                    "id": "CF-101",
                    "is_placeholder": False,
                    "mechanism": "LOXL2 inhibitor",
                }
            ],
        }
        prose = (
            "## 1.0 Cover Letter\n"
            "Phase 1 IND for Alzheimer's. CF-101 is a LOXL2 inhibitor.\n"
            "[UNSIGNED DRAFT — requires human signatory]\n"
        )
        result = validate_ind(clean, prose)
        assert result["validation_status"] == "passed"
        assert result["failures"] == []

    def test_g3_catches_bace_vs_loxl2_contradiction(self):
        manifest = {
            "phase": "1",
            "drugs": [{"id": "drug_1", "is_placeholder": True, "mechanism": "LOXL2 inhibitor"}],
            "sections": {},
        }
        prose = (
            "Drug 1 is a LOXL2 inhibitor in section 2.\n"
            "Later: Drug 1, a selective BACE-1 inhibitor, reduced amyloid.\n"
        )
        result = validate_ind(manifest, prose)
        assert any("G3" in f for f in result["failures"])

    def test_g4_catches_phase2_language_in_prose(self):
        manifest = {"phase": "1", "drugs": [], "sections": {}}
        prose = "A pivotal Phase 2 proof-of-concept study enrolled 212 participants."
        result = validate_ind(manifest, prose)
        assert any("G4" in f for f in result["failures"])

    def test_g6_allows_override_rationale(self):
        manifest = {
            **SAMPLE_MANIFEST,
            "identifiers": [],
            "statistics": [],
            "signatories": [{"name": "Dr. Jane Doe", "verified": True}],
            "selection_override_rationale": "Clinical team selected for safety profile",
            "sections": {},
        }
        prose = "[UNSIGNED DRAFT] Phase 1 IND."
        result = validate_ind(manifest, prose)
        assert not any(f.startswith("G6:") for f in result["failures"])

    def test_sections_list_format_supported(self):
        manifest = {
            "phase": "1",
            "drugs": [],
            "sections": [{"id": "2.2", "status": "present"}],
        }
        prose = "## 2.2 Prior Experience\ndrug_1 had prior exposure.\n"
        result = validate_ind(manifest, prose)
        assert any("G2" in f for f in result["failures"])

    @pytest.mark.skipif(not IND3_PROSE.exists(), reason="IND_3.md sample not available")
    def test_real_ind_sample_from_clickup_fails(self):
        manifest = json.loads(IND3_MANIFEST.read_text(encoding="utf-8"))
        prose = IND3_PROSE.read_text(encoding="utf-8")
        result = validate_ind(manifest, prose)
        assert result["validation_status"] == "failed"
        codes = {f.split(":", 1)[0] for f in result["failures"]}
        assert "G1" in codes
        assert "G3" in codes
        assert "G4" in codes
        assert "G7" in codes
        assert len(result["failures"]) >= 10
