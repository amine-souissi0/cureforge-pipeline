"""Agent 6 — Computer Vision Movement Tracker (stub + design spec) — bilingual EN/RU."""
from __future__ import annotations
from .base import groq_call


def get_design_spec() -> dict:
    """Returns the design specification for the CV agent (no LLM needed)."""
    return {
        "status": "DESIGN_PHASE",
        "description_en": "Computer Vision agent for monitoring physical rehabilitation exercises via camera",
        "description_ru": "Агент компьютерного зрения для мониторинга физических упражнений через камеру",
        "architecture": {
            "input": "Camera feed (phone/tablet camera or IP camera at bedside)",
            "models": [
                "MediaPipe Pose (real-time skeleton tracking, runs on phone)",
                "OpenCV motion analysis (ROM measurement)",
                "Custom classifier: correct vs incorrect exercise form"
            ],
            "output": [
                "Joint angles (elbow, shoulder, wrist, knee)",
                "Range of motion (ROM) measurements per session",
                "Exercise repetition count",
                "Form quality score (0-100)",
                "Session summary fed into patient model"
            ]
        },
        "tracked_exercises": [
            {"name": "Right arm fist open/close", "joints": ["wrist", "fingers"], "metric": "repetitions"},
            {"name": "Right shoulder flexion/extension", "joints": ["shoulder"], "metric": "ROM degrees"},
            {"name": "Right elbow bend", "joints": ["elbow"], "metric": "ROM degrees"},
            {"name": "Right leg raise", "joints": ["hip", "knee"], "metric": "height + repetitions"},
            {"name": "Standing balance", "joints": ["full_body"], "metric": "sway distance"}
        ],
        "data_integration": {
            "feeds_into": "PatientModel.rehab_sessions[]",
            "updates": ["nihss_trajectory", "functional_scales", "recovery_timeline"],
            "reporting": "Automatic session report after each exercise set"
        },
        "implementation_roadmap": [
            {"phase": 1, "weeks": "1-2", "task_en": "Set up MediaPipe on tablet/phone at bedside", "task_ru": "Установить MediaPipe на планшет у кровати"},
            {"phase": 2, "weeks": "3-4", "task_en": "Calibrate for patient body proportions", "task_ru": "Калибровка под параметры пациента"},
            {"phase": 3, "weeks": "5-6", "task_en": "Connect to dashboard (REST API)", "task_ru": "Подключение к дашборду (REST API)"},
            {"phase": 4, "weeks": "7+", "task_en": "Automated progress alerts to family/doctor", "task_ru": "Автоматические оповещения семье/врачу"}
        ],
        "hardware_needed": [
            "Tablet or phone with front camera (existing device OK)",
            "Optional: depth camera (Intel RealSense) for 3D tracking",
            "Wi-Fi connection to upload session data"
        ],
        "privacy_note_en": "All video processed locally on device — no video stored or transmitted",
        "privacy_note_ru": "Всё видео обрабатывается локально на устройстве — никакое видео не хранится и не передаётся"
    }


def run(patient_summary: str, rehab_result: dict) -> dict:
    """Currently returns design spec. Future: process actual CV session data."""
    spec = get_design_spec()
    # In future: parse actual movement data from camera session
    # For now, generate recommendations based on current rehab status
    user = f"""Patient: {patient_summary[:500]}
Rehab status: Rankin 5, Rivermead 2, right arm paresis (makes fist), right leg nearly recovered.

Generate 3 specific computer vision monitoring protocols for this patient's home exercises.
Focus on: (1) right arm ROM tracking, (2) right leg strength, (3) balance monitoring.
Keep recommendations brief and practical for family use."""
    
    llm_recs = groq_call(
        "You are a computer vision and rehabilitation specialist. Return JSON with 'protocols' array.",
        user, json_mode=True, max_tokens=800
    )
    spec["llm_recommendations"] = llm_recs
    return spec
