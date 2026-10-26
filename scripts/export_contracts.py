"""Write `contracts/openapi.yaml` and `contracts/schemas/*.json` from the code.

uv run python scripts/export_contracts.py          # write
uv run python scripts/export_contracts.py --check  # exit 1 if the files are stale
"""

import argparse
import sys
from pathlib import Path

from greenink.core.schemas import render_schemas
from greenink_api.contract import render_openapi

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def expected_files() -> dict[Path, str]:
    files = {CONTRACTS / "openapi.yaml": render_openapi()}
    files.update({CONTRACTS / "schemas" / name: text for name, text in render_schemas().items()})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="fail if the committed files are stale")
    args = parser.parse_args()

    expected = expected_files()
    schema_dir = CONTRACTS / "schemas"
    extra = {p for p in schema_dir.glob("*.json")} - set(expected) if schema_dir.exists() else set()

    if args.check:
        stale = [p for p, text in expected.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in sorted(stale + sorted(extra)):
            print(f"stale: {path.relative_to(CONTRACTS.parent)}", file=sys.stderr)
        return 1 if stale or extra else 0

    schema_dir.mkdir(parents=True, exist_ok=True)
    for path in extra:
        path.unlink()
    for path, text in expected.items():
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(expected)} files under {CONTRACTS.relative_to(CONTRACTS.parent)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
