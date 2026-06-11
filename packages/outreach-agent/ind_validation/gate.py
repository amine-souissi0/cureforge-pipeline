"""Pre-ingestion validation gate (G1–G7). Fail = block FDA packaging."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Union

from ind_validation.schema import INDManifest

logger = logging.getLogger(__name__)

NCT_RE = re.compile(r"NCT\d{8}")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
JOURNAL_YEAR_RE = re.compile(
    r"\b(?:Alzheimer'?s?\s+Res\s+Ther|Mol\s+Neurodegener|J\s+Clin\s+Invest|PNAS|Brain\s+Pathol)"
    r"[^\n]{0,40}\d{4}\b",
    re.I,
)
PLACEHOLDER_TOKENS = (
    r"\[[A-Z_]+_PENDING\]",
    r"drug_\d+",
    r"To be determined",
    r"\[To be assigned\]",
    r"Autonomous Research System",
    r"IND XXXXXX",
)
PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDER_TOKENS), re.I)
FABRICATED_SIGNATORY = re.compile(r"Dr\.\s+Elena\s+M\.\s+Rossi", re.I)
UNSIGNED_DRAFT_OK = re.compile(r"\[UNSIGNED\s+DRAFT", re.I)
SIGNATURE_BLOCK_RE = re.compile(
    r"(?:Sincerely,|Respectfully,).*?(?:\*\*)?Dr\.\s+([A-Z][\w'.-]+(?:\s+[A-Z]\.)?\s+[A-Z][\w'.-]+)",
    re.S | re.I,
)
CLINICAL_CLAIM_RE = re.compile(
    r"NCT\d{8}|~?\d+\s+human\s+subjects?|\d+\s+participants?|adverse\s+event|prior.?IND|"
    r"Phase\s+[23]\b|%\s*(?:AE|adverse)",
    re.I,
)
PHASE2_COMPLETED_PROSE_RE = re.compile(
    r"completed\s+Phase\s*2|Phase\s*2\s+proof[-\s]of[-\s]concept|212\s+participants|"
    r"enrolled\s+212|pivotal\s+Phase\s*2",
    re.I,
)
_HYPHEN = r"[\s\-‑–]?"
MECHANISM_FAMILIES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"LOXL2", re.I), "LOXL2"),
    (re.compile(rf"BACE{_HYPHEN}1", re.I), "BACE-1"),
    (re.compile(r"HSF1", re.I), "HSF-1"),
    (re.compile(rf"tau{_HYPHEN}?(?:phosphorylation|modulator)", re.I), "tau-modulator"),
    (re.compile(rf"IL{_HYPHEN}?6R", re.I), "IL-6R"),
    (re.compile(rf"neuro{_HYPHEN}?inflammatory", re.I), "neuro-inflammatory"),
]


def validate_ind(manifest: Union[INDManifest, dict[str, Any]], prose: str) -> dict[str, Any]:
    """Return manifest dict with validation_status and failures[]."""
    m = manifest if isinstance(manifest, INDManifest) else INDManifest.from_dict(manifest)
    failures: list[str] = []

    failures.extend(_g1_identifiers(m, prose))
    failures.extend(_g2_placeholders_in_present_sections(m, prose))
    failures.extend(_g3_mechanism_consistency(m, prose))
    failures.extend(_g4_study_stage(m, prose))
    failures.extend(_g5_scorecard_narrative(m, prose))
    failures.extend(_g6_selection_sanity(m))
    failures.extend(_g7_signatures(m, prose))

    status: str = "passed" if not failures else "failed"
    out = m.model_dump()
    out["validation_status"] = status
    out["failures"] = failures

    if failures:
        logger.warning(
            "IND validation gate FAILED hypothesis_id=%s failure_count=%d failures=%s",
            m.hypothesis_id or "(unknown)",
            len(failures),
            failures,
        )
    else:
        logger.info(
            "IND validation gate PASSED hypothesis_id=%s",
            m.hypothesis_id or "(unknown)",
        )

    return out


def write_manifest_result(manifest_path: Path, result: dict[str, Any]) -> Path:
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return manifest_path


def _drug_aliases(drug_id: str) -> list[str]:
    match = re.match(r"drug_(\d+)", drug_id, re.I)
    if not match:
        return [drug_id]
    number = match.group(1)
    return [
        drug_id,
        f"drug {number}",
        f"Drug {number}",
        f"Drug\u202f{number}",  # narrow no-break space used in IND_3.md
    ]


def _mechanisms_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for pattern, label in MECHANISM_FAMILIES:
        if pattern.search(text):
            found.add(label)
    return found


def _manifest_mechanism_labels(mechanism: str) -> set[str]:
    return _mechanisms_in_text(mechanism) or {mechanism.strip().lower()}


def _is_real_provenance(provenance: str) -> bool:
    return provenance == "real"


def _g1_identifiers(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []

    for idn in m.identifiers:
        if not _is_real_provenance(idn.provenance):
            failures.append(f"G1: Non-real identifier shipped: {idn.type}={idn.value}")

    for match in NCT_RE.finditer(prose):
        nct = match.group()
        if not any(i.value == nct and _is_real_provenance(i.provenance) for i in m.identifiers):
            failures.append(f"G1: Unverifiable NCT in prose: {nct}")

    for match in DOI_RE.finditer(prose):
        doi = match.group()
        if not any(i.type.upper() == "DOI" and i.value == doi and _is_real_provenance(i.provenance) for i in m.identifiers):
            failures.append(f"G1: Unverifiable DOI in prose: {doi}")

    for match in JOURNAL_YEAR_RE.finditer(prose):
        snippet = match.group().strip()
        failures.append(f"G1: Unresolvable journal-year citation in prose: {snippet}")

    for drug in m.drugs:
        if drug.is_placeholder and _placeholder_drug_has_clinical_claims(drug.id, prose):
            failures.append(f"G1: Clinical claims attached to placeholder drug: {drug.id}")

    for claim in m.claims:
        if _is_real_provenance(claim.provenance):
            continue
        value_text = str(claim.value)
        if value_text and value_text in prose and claim.provenance != "placeholder":
            failures.append(
                f"G1: Non-real claim rendered as bare specific: {claim.field}={value_text} "
                f"(provenance={claim.provenance})"
            )

    return failures


def _placeholder_drug_has_clinical_claims(drug_id: str, prose: str) -> bool:
    for alias in _drug_aliases(drug_id):
        for match in re.finditer(re.escape(alias), prose, re.I):
            window = prose[max(0, match.start() - 200) : match.end() + 400]
            if CLINICAL_CLAIM_RE.search(window):
                return True
    return bool(NCT_RE.search(prose) and drug_id.lower() in prose.lower())


def _forbidden_placeholder_in_text(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text))


def _section_blocks(m: INDManifest, prose: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for section_id in m.sections:
        pattern = re.compile(
            rf"##\s*{re.escape(section_id)}[^\n]*\n(.*?)(?=\n##\s|\Z)",
            re.S | re.I,
        )
        hit = pattern.search(prose)
        blocks[section_id] = hit.group(1) if hit else ""
    return blocks


def _g2_placeholders_in_present_sections(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []
    if not m.sections:
        if _forbidden_placeholder_in_text(prose):
            failures.append("G2: Placeholder token in prose with no section map")
        return failures

    blocks = _section_blocks(m, prose)
    for section_id, meta in m.sections.items():
        if meta.status != "present":
            continue
        text = blocks.get(section_id) or prose
        if _forbidden_placeholder_in_text(text):
            failures.append(f"G2: Placeholder in present section {section_id}")
    return failures


def _g3_mechanism_consistency(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []
    for drug in m.drugs:
        if not drug.mechanism:
            continue
        mechanisms_found: set[str] = set()
        for alias in _drug_aliases(drug.id):
            for match in re.finditer(re.escape(alias), prose, re.I):
                window = prose[max(0, match.start() - 120) : match.end() + 320]
                mechanisms_found |= _mechanisms_in_text(window)

        if len(mechanisms_found) > 1:
            failures.append(
                f"G3: Contradictory mechanisms for {drug.id}: {sorted(mechanisms_found)}"
            )
            continue

        manifest_labels = _manifest_mechanism_labels(drug.mechanism)
        if mechanisms_found and not mechanisms_found.intersection(manifest_labels):
            failures.append(
                f"G3: Mechanism mismatch for {drug.id} "
                f"(manifest: {drug.mechanism}; prose: {sorted(mechanisms_found)})"
            )
    return failures


def _g4_study_stage(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []
    phase = m.phase.lower()
    is_phase_1 = "phase 1" in phase or phase.strip() in {"1", "phase1"}

    if is_phase_1 and PHASE2_COMPLETED_PROSE_RE.search(prose):
        failures.append("G4: Phase 1 IND prose claims completed Phase 2 human study")

    for stat in m.statistics:
        stage = (stat.study_stage or "").lower()
        if is_phase_1 and "phase 2" in stage:
            failures.append(f"G4: Phase 1 IND with Phase 2 statistic: {stat.label or stat.value}")
        if "preclinical" in stage and "completed" in stage and "participant" in stage:
            failures.append(f"G4: Contradictory study stage: {stat.study_stage}")

    for claim in m.claims:
        stage = (claim.study_stage or "").lower()
        if is_phase_1 and ("phase 2" in stage or "phase_2" in stage):
            failures.append(
                f"G4: Phase 1 IND with Phase 2 claim: {claim.field} study_stage={claim.study_stage}"
            )

    return failures


def _g5_scorecard_narrative(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []
    claims_coverage = re.search(
        r"hallmark coverage|targets?\s+\d+\s+hallmarks?|multi[-\s]target approach",
        prose,
        re.I,
    )
    if (not m.hallmark_targets or m.aging_coverage_score == 0) and claims_coverage:
        failures.append("G5: Narrative claims hallmark coverage but scorecard is zero")
    return failures


def _g6_selection_sanity(m: INDManifest) -> list[str]:
    failures: list[str] = []
    if not m.alternatives or m.selection_override_rationale.strip():
        return failures
    best = max(m.alternatives, key=lambda h: h.acs)
    if m.selected_hypothesis.acs < best.acs:
        failures.append(
            f"G6: Selected hypothesis ACS {m.selected_hypothesis.acs} below alternative {best.acs}"
        )
    return failures


def _g7_signatures(m: INDManifest, prose: str) -> list[str]:
    failures: list[str] = []
    if UNSIGNED_DRAFT_OK.search(prose):
        return failures

    for sig in m.signatories:
        if sig.name and not sig.verified:
            failures.append(f"G7: Unverified signatory in manifest: {sig.name}")

    if FABRICATED_SIGNATORY.search(prose):
        failures.append("G7: Fabricated signatory Dr. Elena M. Rossi in prose")

    for match in SIGNATURE_BLOCK_RE.finditer(prose):
        name = match.group(1).strip()
        if not any(s.verified and s.name and name.lower() in s.name.lower() for s in m.signatories):
            failures.append(f"G7: Unverified signatory in prose: Dr. {name}")

    return failures
