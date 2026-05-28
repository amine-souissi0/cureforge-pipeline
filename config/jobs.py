"""
Job definition registry — all open positions and their matching criteria.
Add/remove jobs here; no code changes required elsewhere.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class JobDefinition:
    id: str
    title: str
    team: str
    levels: List[str]           # which seniority levels fit: junior/mid/senior/staff/principal
    required_skills: List[str]  # must-have — used for matching score
    nice_to_have: List[str]     # bonus skills
    location: str
    remote_ok: bool
    description: str            # the JD text shown to the candidate
    task_corpus_pattern: Optional[str] = None  # override corpus pattern for task generation


JOBS: dict[str, JobDefinition] = {
    j.id: j
    for j in [
        JobDefinition(
            id="jd-be-001",
            title="Backend Engineer",
            team="Platform",
            levels=["junior", "mid", "senior"],
            required_skills=["Python", "REST APIs", "databases", "async programming"],
            nice_to_have=["FastAPI", "PostgreSQL", "Redis", "Docker", "Celery", "Kafka"],
            location="Remote",
            remote_ok=True,
            description=(
                "We're building the core data platform powering our research workflows. "
                "You'll own backend services that ingest, validate, and transform structured "
                "scientific data at scale.\n\n"
                "What you'll work on:\n"
                "- Design and own high-throughput ingestion services (10k+ events/sec)\n"
                "- Build validation layers that enforce data contracts across pipeline stages\n"
                "- Write deterministic, fail-closed error handling — no silent data loss\n"
                "- Collaborate with research scientists to expose clean internal APIs\n\n"
                "Strong Python fundamentals and production async experience required."
            ),
            task_corpus_pattern="pipeline_record_validator",
        ),
        JobDefinition(
            id="jd-de-001",
            title="Data Engineer",
            team="Research Data",
            levels=["mid", "senior"],
            required_skills=["Python", "data pipelines", "SQL", "ETL"],
            nice_to_have=["dbt", "Airflow", "Kafka", "Snowflake", "PostgreSQL", "Spark"],
            location="Remote",
            remote_ok=True,
            description=(
                "Design and maintain the pipelines that move and transform our research data. "
                "You'll ensure data quality, reliability, and accessibility across our organisation.\n\n"
                "What you'll work on:\n"
                "- Build robust ETL workflows from experimental data sources\n"
                "- Own data quality checks, reconciliation, and anomaly detection\n"
                "- Partner with scientists to model data in ways that support analysis\n"
                "- Maintain pipeline observability and alerting\n\n"
                "Strong SQL and production pipeline experience required."
            ),
            task_corpus_pattern="measurement_stream_processor",
        ),
        JobDefinition(
            id="jd-ml-001",
            title="ML Infrastructure Engineer",
            team="Research Platform",
            levels=["senior", "staff", "principal"],
            required_skills=["Python", "machine learning", "distributed systems", "data engineering"],
            nice_to_have=["PyTorch", "Kubernetes", "MLflow", "Kafka", "Spark", "Ray"],
            location="Remote",
            remote_ok=True,
            description=(
                "Support our research team by building reliable ML training infrastructure, "
                "experiment tracking, and model serving pipelines.\n\n"
                "What you'll work on:\n"
                "- Build and maintain experiment checkpointing + replay infrastructure\n"
                "- Own model serving pipelines — low-latency, high-reliability\n"
                "- Instrument training runs for cost and compute observability\n"
                "- Translate experimental research workflows into production-grade systems\n\n"
                "Deep distributed systems experience and ML familiarity required."
            ),
            task_corpus_pattern="checkpoint_simulation_runner",
        ),
    ]
}
