"""
Job definition registry — all open positions at LongevityInTime.
CureForge is a longevity science company building the data and AI infrastructure
to measure, track, and extend human healthspan.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class JobDefinition:
    id: str
    title: str
    team: str
    levels: List[str]
    required_skills: List[str]
    nice_to_have: List[str]
    location: str
    remote_ok: bool
    description: str
    task_corpus_pattern: Optional[str] = None


JOBS: dict[str, JobDefinition] = {
    j.id: j
    for j in [
        JobDefinition(
            id="jd-be-001",
            title="Senior Backend Engineer — Biomarker Data Platform",
            team="Platform Engineering",
            levels=["mid", "senior"],
            required_skills=["Python", "REST APIs", "PostgreSQL", "async programming", "data validation"],
            nice_to_have=["FastAPI", "Redis", "Docker", "Celery", "Kafka", "dbt"],
            location="Remote (US/EU)",
            remote_ok=True,
            description=(
                "At LongevityInTime, we're building the data infrastructure that powers longevity science. "
                "Our platform ingests millions of biomarker measurements daily — blood panels, "
                "wearable signals, and lab assay outputs — and transforms them into the reliable, "
                "structured data our scientists use to understand human healthspan.\n\n"
                "As a Senior Backend Engineer on the Biomarker Data Platform team, you'll own the "
                "services that sit between raw instrument output and our research layer. "
                "Data quality here isn't an abstract concern — a missed null or a silent pipeline "
                "failure can invalidate months of research.\n\n"
                "What you'll work on:\n"
                "- Design and own high-throughput biomarker ingestion services (10k+ events/sec)\n"
                "- Build validation layers that enforce data contracts across pipeline stages\n"
                "- Write deterministic, fail-closed error handling — no silent data loss\n"
                "- Collaborate with research scientists to expose clean, well-documented internal APIs\n"
                "- Own pipeline observability: alerting, cost tracking, SLA dashboards\n\n"
                "We care deeply about correctness. You'll be expected to write code that is explicit, "
                "testable, and safe to operate in production without hand-holding.\n\n"
                "Strong Python fundamentals and production async experience required. "
                "Curiosity about longevity science is a plus."
            ),
            task_corpus_pattern="pipeline_record_validator",
        ),
        JobDefinition(
            id="jd-de-001",
            title="Data Engineer — Research Data Pipelines",
            team="Research Data",
            levels=["mid", "senior"],
            required_skills=["Python", "data pipelines", "SQL", "ETL", "data quality"],
            nice_to_have=["dbt", "Airflow", "Kafka", "Snowflake", "PostgreSQL", "Spark", "Great Expectations"],
            location="Remote (US/EU)",
            remote_ok=True,
            description=(
                "LongevityInTime's research team runs continuous studies tracking healthspan markers "
                "across cohorts of participants. Every study generates streams of measurement "
                "events — lab results, wearable data, self-reported assessments — that need to "
                "be ingested, validated, joined, and made available for analysis without delay.\n\n"
                "As a Data Engineer on the Research Data team, you'll build and maintain the "
                "pipelines that keep our science moving. You'll work closely with computational "
                "biologists and data scientists who depend on clean, well-modelled data to do "
                "their best work.\n\n"
                "What you'll work on:\n"
                "- Build robust ETL workflows from diverse experimental data sources (lab instruments, "
                "wearables, EHR exports)\n"
                "- Own data quality checks, anomaly detection, and reconciliation across sources\n"
                "- Model data in ways that support both ad-hoc research queries and production analytics\n"
                "- Maintain pipeline observability, lineage, and alerting\n"
                "- Partner with scientists to turn experimental workflows into reliable, repeatable pipelines\n\n"
                "Strong SQL and production pipeline experience required. "
                "Exposure to life sciences or clinical data is a strong plus."
            ),
            task_corpus_pattern="measurement_stream_processor",
        ),
        JobDefinition(
            id="jd-ml-001",
            title="ML Infrastructure Engineer — Healthspan Models",
            team="Research Platform",
            levels=["senior", "staff", "principal"],
            required_skills=["Python", "machine learning", "distributed systems", "MLOps", "data engineering"],
            nice_to_have=["PyTorch", "Kubernetes", "MLflow", "Weights & Biases", "Kafka", "Ray", "Spark"],
            location="Remote (US/EU)",
            remote_ok=True,
            description=(
                "Our research team is building predictive models that estimate biological age, "
                "detect early markers of accelerated aging, and evaluate the effectiveness of "
                "interventions. These models are only as good as the infrastructure that trains, "
                "validates, and serves them.\n\n"
                "As an ML Infrastructure Engineer, you'll build the systems that let our scientists "
                "iterate fast without compromising reproducibility. Experiment tracking, model "
                "versioning, serving pipelines, and compute orchestration are your domain.\n\n"
                "What you'll work on:\n"
                "- Build and maintain experiment checkpointing, replay, and reproducibility infrastructure\n"
                "- Own model serving pipelines — low-latency, high-reliability scoring at scale\n"
                "- Instrument training runs for cost and compute observability\n"
                "- Translate experimental research workflows into production-grade, auditable systems\n"
                "- Partner with computational biologists to operationalise new model architectures\n\n"
                "Deep distributed systems experience and hands-on ML engineering required. "
                "Experience with clinical or biomedical data is a significant plus."
            ),
            task_corpus_pattern="checkpoint_simulation_runner",
        ),
        JobDefinition(
            id="jd-staff-001",
            title="Staff Engineer — Longevity Data Infrastructure",
            team="Engineering",
            levels=["staff", "principal"],
            required_skills=["Python", "distributed systems", "data architecture", "technical leadership", "API design"],
            nice_to_have=["Kafka", "Kubernetes", "PostgreSQL", "Snowflake", "dbt", "Terraform", "Ray"],
            location="Remote (US/EU)",
            remote_ok=True,
            description=(
                "LongevityInTime is at an inflection point. We've proven that our platform works — now "
                "we're scaling it to support 10x the participants, 10x the data volume, and a "
                "growing team of engineers and scientists who depend on it daily.\n\n"
                "As a Staff Engineer, you'll set the technical direction for our core data "
                "infrastructure. You'll define the architecture patterns the team builds on, "
                "identify systemic risks before they become incidents, and mentor engineers at "
                "every level.\n\n"
                "What you'll work on:\n"
                "- Own the architectural roadmap for our biomarker ingestion and processing platform\n"
                "- Define data contracts, schema standards, and API design patterns across teams\n"
                "- Lead our most complex cross-functional technical initiatives\n"
                "- Set the bar for system reliability, observability, and operational excellence\n"
                "- Mentor senior and mid-level engineers; lead technical design reviews\n\n"
                "You've done this before — you've scaled a data platform through hypergrowth and "
                "know what breaks first. You write code, review code, and influence architecture "
                "in equal measure."
            ),
            task_corpus_pattern="type_enforced_pipeline",
        ),
    ]
}
