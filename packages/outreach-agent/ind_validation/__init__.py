"""IND pre-ingestion validation gate — blocks fabricated content before FDA packaging."""

from ind_validation.gate import validate_ind, write_manifest_result
from ind_validation.schema import INDManifest

__all__ = ["INDManifest", "validate_ind", "write_manifest_result"]
