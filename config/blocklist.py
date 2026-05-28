"""
Fail-closed blocklist for task decomposer.

Any task that touches these topics must be rejected, even if the connection
is ambiguous. Ambiguous → FAIL, not PASS.
"""

BLOCKED_TOPICS: list[str] = [
    # Domain-specific (proprietary)
    "longevity",
    "aging",
    "lifespan",
    "epigenetic",
    "biomarker",
    "gene expression",
    "clinical trial",
    "patient data",
    "health record",
    "medical record",
    "diagnostic",
    "treatment protocol",
    # Internal systems
    "longevity_engine",
    "longevityintime_internal",
    "biological_clock",
    # Security-sensitive
    "authentication bypass",
    "privilege escalation",
    "sql injection",
    "remote code execution",
    "cryptographic key",
]
