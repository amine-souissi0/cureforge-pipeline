"""
Canonical patient model — Pydantic schema for CureForge patient simulation.
Updated: 04.06.2026 — from Этапный эпикриз (Interim Report) 03.06.2026
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field


class Demographics(BaseModel):
    patient_id: str = "OIT-001"
    full_name: str = "Teterin Oleg Ivanovich (Тетерин Олег Иванович)"
    name_initials: str = "O.I.T."
    dob: str = "26.09.1942"
    age: int = 83
    sex: str = "male"
    native_language: str = "Russian"
    other_languages: List[str] = ["English", "Swahili"]
    africa_residence_years: int = 27
    africa_region: str = "Eastern Africa (1978–2005)"
    smoking: str = "1 pack/day (heavy)"
    institution: str = "GKB im M.P. Konchalovskogo, Zelenograd, Moscow"
    oms_policy: str = "7700001073760942"
    admission_date: str = "2026-05-26 18:22"
    hospital_days: int = 8


class NeurologicalStatus(BaseModel):
    stroke_type: str = "ischemic"
    stroke_date: str = "2026-05-27"
    mechanism: str = "post-CEA ICA thrombus (10 cm), left MCA terminal branches"
    infarct_location: str = "left frontal cortex M4-M5"
    infarct_size_mm: float = 15.0
    aspects_score: int = 8
    aspects_source: str = "CT 28.05.2026 — human radiologist report (EMIAS)"
    # CORRECTED from interim report 03.06.2026 — minimum confirmed 12
    nihss_trajectory: List[dict] = Field(default_factory=lambda: [
        {"date": "2026-05-27", "score": 15, "note": "admission"},
        {"date": "2026-05-28", "score": 18, "note": "worsening D1"},
        {"date": "2026-05-29", "score": 14, "note": "recovery D3"},
        {"date": "2026-05-30", "score": 12, "note": "latest — confirmed minimum"},
    ])
    # Functional scales (03.06.2026 interim report)
    rankin_scale: int = 5       # Modified Rankin Scale — severe disability
    rivermead_index: int = 2    # Rivermead Mobility Index — minimal mobility
    srm_score: int = 5          # Stroke Rehabilitation Measure
    # CORRECTED: complex aphasia (not just Broca's) + dysarthria
    aphasia_type: str = "complex motor aphasia + gross dysarthria"
    aphasia_comprehension: str = "preserved"
    sensory_aphasia: str = "resolved (clinical, Day 3)"
    right_arm: str = "paresis persists — makes fist, limited active movement"
    right_leg: str = "nearly recovered — active movements present"
    swallowing: str = "preserved (clinical) — formal GUSS not yet done"
    consciousness: str = "clear, oriented in space/time/person"
    cognitive_impairment: str = "present — cognitive deficits noted in ICD diagnosis"
    facial_asymmetry: str = "mild right-sided"
    rehabilitation_stage: str = "Stage 2 planned — interim report prepared for handover"
    clinical_trajectory: str = "IMPROVEMENT (улучшение) — 03.06.2026"


class Comorbidities(BaseModel):
    cardiac_af: str = "permanent AF, normosystolic — HR 66-83-113 bpm (02.06.2026)"
    cha2ds2_vasc: int = 4
    has_bled: int = 1
    ecg_02jun26: str = "AF normosystole HR 66-83-113, axis 14° horizontal, repolarization disturbance (nonspecific)"
    ecg_trend: str = "29.05→30.05→02.06: extrasystole RESOLVED, scar suspicion REMOVED on trend"
    lvef_pct: float = 56.0
    echo_findings: str = "LVEF 56%, no focal WMA, Mitral regurg Gr1, Tricusp regurg Gr1, Aortic calcification, RVSP 17mmHg"
    weight_kg: float = 70.0
    height_cm: int = 176
    bmi: float = 22.6
    aortic_valve: str = "calcification — leaflets thickened"
    anteroseptal_scar: str = "REMOVED — 3-ECG trend shows no scar; echo needed for final confirmation"
    right_ica_plaque: str = "35–40% (Plaque RADS III) — surveillance"
    left_ica: str = "occluded post-op — compensated via circle of Willis"
    lower_limb_atherosclerosis: str = "severe, multiple stents, left toe amputation (metatarsal 2023)"
    ckd_stage: str = "G2 (eGFR 76.7 mL/min/1.73m²) — dose-adjust renally-cleared drugs"
    liver: str = "diffuse changes on US"
    pancreas: str = "diffuse changes on US"
    lungs: str = "pneumosclerosis + chronic bronchitis"
    hip: str = "left hip arthroplasty — MRI conditional 1.5T only"
    foot: str = "left toes 1–5 amputated (metatarsal amputation 2023)"
    # UPDATED from interim report
    crp_mg_l: float = 22.95   # 29.05.2026 — elevated (was 14.6)
    wbc_29may: float = 15.26   # improving (was 17.4 on 27.05)
    wbc_30may: float = 9.45    # normalised
    eosinophils_abs: float = 0.04   # LOW — weakens tropical/Africa hypothesis
    eosinophils_pct: float = 0.24   # below normal range
    inr_admission: float = 2.08    # elevated on admission
    glucose_mmol: float = 9.27     # elevated (27.05.2026)
    uti_active: bool = True         # confirmed by urinalysis (WBC >100/HPF)
    hematuria: str = "erythrocytes >100/HPF in urinalysis — monitoring required"
    coagulogram_result: Optional[str] = "Enoxaparin course completed (30.05-03.06.2026, 5 days). INR 2.08 on admission. Long-term anticoagulation for AF decision PENDING."
    anticoagulation_status: str = "Enoxaparin COMPLETED. Aspirin 125mg ongoing. Long-term AC decision pending."


class Medications(BaseModel):
    """Current medications as of 03.06.2026 (from Этапный эпикриз)"""
    atorvastatin_20mg: str = "oral, once daily evening, 30.05-08.06.2026 (lipid-lowering)"
    aspirin_125mg: str = "oral, once daily evening, 30.05-08.06.2026 (antiplatelet)"
    enoxaparin_8000: str = "SC twice daily, 30.05-03.06.2026 COMPLETED (anticoagulant, 5 days)"
    ampicillin_sulbactam: str = "IV 3x/day (6:00,14:00,22:00), 31.05-08.06.2026 (antibiotic — UTI/post-op)"
    valsartan_40mg: str = "oral twice daily (antihypertensive, ongoing)"
    bisoprolol_5mg: str = "oral once daily morning (rate control + antihypertensive, ongoing)"
    amlodipine_5mg: str = "oral once daily morning (antihypertensive)"
    omeprazole_20mg: str = "oral once daily morning (gastroprotection, ongoing)"
    mexidol_500mg: str = "IV infusion once daily, 31.05-03.06.2026 (neuroprotective/metabolic)"
    cerebrolysin: str = "IV 10ml once daily (neuroprotective, ongoing)"
    lactitol_10g: str = "oral, single dose 31.05.2026 (laxative)"


class Imaging(BaseModel):
    # ZIP 1 — Neck CTA (original)
    zip1_file: str = "5426422154.zip"
    zip1_study_date: str = "2026-05-27"
    zip1_modality: str = "CT"
    zip1_body_part: str = "NECK"
    zip1_slices: int = 2060
    zip1_note: str = "Neck CTA — carotid assessment post-CEA"

    # ZIP 2 — Brain CT Day 1
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
    zip2_note: str = "Brain CT Day 1 — 347 slices — HEAD confirmed"

    # ZIP 3 — Follow-up Brain CT Day 2
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
    zip3_note: str = "Follow-up Brain CT Day 2 (28.05.2026) — no hemorrhagic transformation, ASPECTS 8"

    # MRI from report
    mri_available: bool = True
    mri_note: str = "MRI 27.05.2026 — acute ischemic stroke left MCA terminal branches. Fazekas 2, GCA 1"

    brain_ct_available: bool = True
    followup_ct_available: bool = True
    aspects_from_radiologist: str = "ASPECTS 8 — left frontal cortex M4-M5 infarct — no hemorrhage — no edema (28.05.2026)"
    imaging_gap: str = "All major imaging completed. MRI DICOM ZIP not yet provided."
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
    schema_version: str = "1.2"
    assessment_date: str = Field(default_factory=lambda: datetime.utcnow().date().isoformat())
    demographics: Demographics = Field(default_factory=Demographics)
    neurology: NeurologicalStatus = Field(default_factory=NeurologicalStatus)
    comorbidities: Comorbidities = Field(default_factory=Comorbidities)
    medications: Medications = Field(default_factory=Medications)
    imaging: Imaging = Field(default_factory=Imaging)
    outputs: AgentOutputs = Field(default_factory=AgentOutputs)

    def to_clinical_summary(self) -> str:
        d = self.demographics
        n = self.neurology
        c = self.comorbidities
        m = self.medications
        img = self.imaging
        return f"""PATIENT: {d.name_initials} | {d.age}y | {d.sex} | {d.native_language}/{'/'.join(d.other_languages)}
ADMISSION: {d.admission_date} | Day {d.hospital_days}
STROKE: {n.stroke_type} | {n.stroke_date} | {n.mechanism}
LOCATION: {n.infarct_location} | ASPECTS {n.aspects_score} | NIHSS latest: {n.nihss_trajectory[-1]['score']}
NIHSS TRAJECTORY: {' → '.join(str(x['score']) for x in n.nihss_trajectory)} (admission→D1→D3→latest)
FUNCTIONAL SCALES: Rankin {n.rankin_scale} | Rivermead {n.rivermead_index} | SRM {n.srm_score}
DEFICITS: {n.aphasia_type} | arm={n.right_arm[:50]} | leg={n.right_leg[:40]}
COGNITION: {n.cognitive_impairment}
TRAJECTORY: {n.clinical_trajectory}
CARDIAC: {c.cardiac_af} | LVEF {c.lvef_pct}% | CHA2DS2-VASc {c.cha2ds2_vasc} | ECG: {c.ecg_02jun26}
VASCULAR: R-ICA {c.right_ica_plaque} | L-ICA {c.left_ica[:40]}
RENAL: {c.ckd_stage} | CRP {c.crp_mg_l} mg/L | INR-admission {c.inr_admission}
LABS: WBC 30.05={c.wbc_30may} (normalised) | Glucose {c.glucose_mmol} mmol/L | Eosinophils {c.eosinophils_pct}% (LOW)
UTI: {c.uti_active} | Hematuria: {c.hematuria}
ANTICOAGULATION: {c.anticoagulation_status}
SMOKING: {d.smoking} | AFRICA: {d.africa_residence_years}y ({d.africa_region}) | Eosinophils LOW — tropical hypothesis WEAKENED
ORTHOPEDIC: {c.hip} | {c.foot}
MEDICATIONS (active): Aspirin 125mg | Bisoprolol 5mg | Valsartan 40mg | Amlodipine 5mg | Atorvastatin 20mg | Ampicillin+Sulbactam IV | Omeprazole | Cerebrolysin
IMAGING: {img.zip3_note}
MRI: {img.mri_note}
REHAB: {n.rehabilitation_stage}"""
