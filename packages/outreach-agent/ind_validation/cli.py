"""CLI: validate IND manifest + prose before FDA packaging."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ind_validation.gate import validate_ind, write_manifest_result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="IND pre-ingestion validation gate")
    p.add_argument("--manifest", required=True, help="Path to manifest JSON")
    p.add_argument("--prose", required=True, help="Path to IND markdown")
    p.add_argument("--write", action="store_true", help="Write validation result back to manifest")
    args = p.parse_args(argv)

    manifest_path = Path(args.manifest)
    prose_path = Path(args.prose)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prose = prose_path.read_text(encoding="utf-8")

    result = validate_ind(manifest, prose)
    if args.write:
        write_manifest_result(manifest_path, result)

    print(json.dumps({"validation_status": result["validation_status"], "failures": result["failures"]}, indent=2))
    return 0 if result["validation_status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
