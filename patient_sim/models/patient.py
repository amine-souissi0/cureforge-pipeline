"""
Canonical patient model — Pydantic schema for CureForge patient simulation.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field


class Demographics(BaseModel):
    patient_id: str = "OIT-001"
    name_initials: str = "O.I.T."
    age: int = 83
    sex: str = "male"
    native_language: str = "Russian"
    other_languages: List[str] = ["English", "Swahili"]
    africa_residence_years: int = 27
    africa_region: str = "Eastern Africa (1978–2005)"
    smoking: str = "1 pack/day (heavy)"
    institution: str = "GKB im M.P. Konchalovskogo, Zelenograd, Moscow"


class NeurologicalStatus(BaseModel):
    stroke_type: str = "ischemic"
    stroke_date: str = "2026-05-27"
    mechanism: str = "post-CEA ICA thrombus (10 cm), left MCA terminal branches"
    infarct_location: str = "left frontal cortex M4-M5"
    infarct_size_mm: float = 15.0
    aspects_score: int = 8
    aspects_source: str = "CT 28.05.2026 — human radiologist report (EMIAS)"
    nihss_trajectory: List[dict] = Field(default_factory=lambda: [
        {"date": "2026-05-27", "score": 15, "note": "admission"},
        {"date": "2026-05-28", "score": 18, "note": "worsening D1"},
        {"date": "2026-05-29", "score": 14, "note": "recovery"},
        {"date": "2026-05-30", "score": 12, "note": "latest — confirmed minimum (corrected from earlier 7-9 error)"},
    ])
    aphasia_type: str = "motor (Broca's)"
    aphasia_comprehension: str = "preserved"
    sensory_aphasia: str = "resolved (clinical, Day 3 — reassess)"
    right_arm: str = "paresis persists — makes fist, limited active movement"
    right_leg: str = "nearly recovered — active movements present"
    swallowing: str = "preserved (clinical) — formal GUSS not yet done"
    consciousness: str = "conscious, oriented, follows commands"
    facial_asymmetry: str = "mild right-sided"


class Comorbidities(BaseModel):
    cardiac_af: str = "atrial fibrillation, normosystolic HR 66-83-113 bpm (min-mean-max)"
    blood_pressure: str = "stable, monitoring during rehabilitation"
    ecg_trend: str = "29.05→30.05→02.06: transient extrasystole resolved, rhythm stably controlled"
    lvef_pct: float = 56.0
    bp_02jun26: str = "02.06.26 updates — BP and pulse to be confirmed from clinical notes"
    aortic_valve: str = "calcification"
    anteroseptal_scar: str = "SUSPECTED on ECG — unconfirmed; echo planned"
    right_ica_plaque: str = "35–40% (Plaque RADS III) — surveillance"
    left_ica: str = "occluded post-op — compensated via circle of Willis"
    lower_limb_atherosclerosis: str = "severe, multiple stents, left toe amputation"
    ckd_stage: str = "G2 (eGFR ~74) — dose-adjust all renally-cleared drugs"
    liver: str = "diffuse changes on US"
    pancreas: str = "diffuse changes on US"
    lungs: str = "pneumosclerosis + chronic bronchitis"
    hip: str = "left hip arthroplasty — MRI conditional 1.5T only"
    foot: str = "left toes 1–5 amputated"
    crp_mg_l: float = 14.6
    uti_active: bool = True
    coagulogram_result: Optional[str] = None


class Imaging(BaseModel):
    # ZIP 1 — Neck CTA (original)
    zip1_file: str = "5426422154.zip"
    zip1_study_date: str = "2026-05-27"
    zip1_modality: str = "CT"
    zip1_body_part: str = "NECK"
    zip1_slices: int = 2060
    zip1_note: str = "Neck CTA — carotid assessment post-CEA"

    # ZIP 2 — Brain CT (NEW — 5426422151.zip)
    zip2_file: str = "5426422151.zip"
    zip2_study_date: str = "2026-05-27"
    zip2_modality: str = "CT"
    zip2_body_part: str = "HEAD"
    zip2_slices: int = 347
    zip2_manufacturer: str = "GE Revolution Maxima"
    zip2_kvp: int = 120
    zip2_slice_thickness_mm: float = 0.625
    zip2_pixel_spacing_mm: float = 0.582
    zip2_coverage_mm: int = 205
    zip2_window: str = "C350/W2000 — brain parenchyma protocol"
    zip2_note: str = "Brain CT confirmed — 347 slices — HEAD body part"

    # ZIP 3 — Follow-up Brain CT Day 2 (5426422543.zip)
    zip3_file: str = "5426422543.zip"
    zip3_study_date: str = "2026-05-28"
    zip3_modality: str = "CT"
    zip3_body_part: str = "HEAD"
    zip3_slices: int = 323
    zip3_manufacturer: str = "GE Revolution Maxima"
    zip3_kvp: int = 80
    zip3_slice_thickness_mm: float = 0.625
    zip3_coverage_mm: int = 261
    zip3_window: str = "C150/W1500 — brain/soft-tissue (low-dose Day 2 follow-up)"
    zip3_note: str = "Follow-up Brain CT Day 2 (28.05.2026) — confirms no hemorrhagic transformation, no malignant MCA, penumbra zone"

    brain_ct_available: bool = True
    followup_ct_available: bool = True
    mri_available: bool = False
    aspects_from_radiologist: str = "ASPECTS 8 — left frontal cortex M4-M5 infarct — no hemorrhage — no edema (28.05.2026 report)"
    imaging_gap: str = "MRI not provided — 3 of 3 CTs processed"
    all_zips_processed: bool = True


class AgentOutputs(BaseModel):
    ingestion_complete: bool = False
    cds_complete: bool = False
    recovery_complete: bool = False
    report_complete: bool = False
    ingestion_result: Dict[str, Any] = Field(default_factory=dict)
    cds_result: Dict[str, Any] = Field(default_factory=dict)
    recovery_result: Dict[str, Any] = Field(default_factory=dict)
    report_markdown: str = ""
    report_markdown_ru: str = ""
    run_timestamp: Optional[str] = None
    run_duration_seconds: Optional[float] = None


class PatientModel(BaseModel):
    schema_version: str = "1.1"
    assessment_date: str = Field(default_factory=lambda: datetime.utcnow().date().isoformat())
    demographics: Demographics = Field(default_factory=Demographics)
    neurology: NeurologicalStatus = Field(default_factory=NeurologicalStatus)
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    imaging: Imaging = Field(default_factory=Imaging)
    outputs: AgentOutputs = Field(default_factory=AgentOutputs)

    def to_clinical_summary(self) -> str:
        d = self.demographics
        n = self.neurology
        c = self.comorbidities
        img = self.imaging
        return f"""PATIENT: {d.name_initials} | {d.age}y | {d.sex} | {d.native_language}/{'/'.join(d.other_languages)}
STROKE: {n.stroke_type} | {n.stroke_date} | {n.mechanism}
LOCATION: {n.infarct_location} | ASPECTS {n.aspects_score} | NIHSS latest: {n.nihss_trajectory[-1]['score']}
NIHSS TRAJECTORY: {' → '.join(str(x['score']) for x in n.nihss_trajectory)} (Day 1 to Day 4)
DEFICITS: aphasia={n.aphasia_type} (comprehension {n.aphasia_comprehension}) | arm={n.right_arm[:50]} | leg={n.right_leg[:40]}
SWALLOWING: {n.swallowing}
CARDIAC: AF HR~87bpm | LVEF {c.lvef_pct}% | scar={c.anteroseptal_scar[:40]}
VASCULAR: R-ICA {c.right_ica_plaque} | L-ICA {c.left_ica[:40]}
RENAL: {c.ckd_stage} | CRP {c.crp_mg_l} mg/L | UTI={c.uti_active}
SMOKING: {d.smoking} | AFRICA: {d.africa_residence_years}y ({d.africa_region})
ORTHOPEDIC: {c.hip} | {c.foot}
COAGULOGRAM: {c.coagulogram_result or 'PENDING — required before anticoagulation decision'}
IMAGING ZIP1: {img.zip1_body_part} CTA — {img.zip1_slices} slices
IMAGING ZIP2: {img.zip2_body_part} CT — {img.zip2_slices} slices — {img.zip2_manufacturer} — {img.zip2_note}
ASPECTS SOURCE: {img.aspects_from_radiologist}"""
