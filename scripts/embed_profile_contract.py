"""Embed field sets and output columns into profile JSON files on disk.

The database migration ``024_embed_profile_contract`` rewrites stored
profiles. Profiles that live as JSON files (the golden corpus, the test
profiles, the gitignored eval cases, and any ``supplier_profiles/`` seeds)
need the same rewrite, with the same pure function, so this script loads the
migration module and applies ``embed_contract`` to each file.

Usage (from the repo root):

    python scripts/embed_profile_contract.py                 # dry run, default folders
    python scripts/embed_profile_contract.py --apply
    python scripts/embed_profile_contract.py --check         # exit 1 if any file is stale
    python scripts/embed_profile_contract.py --spec-json standard.time_and_material=path/to/spec.json
    python scripts/embed_profile_contract.py path/to/profile.json --apply

``--spec-json id=path`` / ``--schema-json id=path`` supply a registry record
that a profile names but that never lived in ``output_specs/`` /
``field_schemas/`` on disk.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "migrations" / "versions" / "024_embed_profile_contract.py"

DEFAULT_TARGETS = (
    "tests/fixtures/corpus/*/profile.json",
    "supplier_profiles_test/*.json",
    "supplier_profiles/*.json",
    "eval_cases/*/profile.json",
)


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_024", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_records(pairs: list[str], id_key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for pair in pairs:
        record_id, _, path = pair.partition("=")
        if not path:
            raise SystemExit(f"expected id=path, got {pair!r}")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out[record_id or data.get(id_key, "")] = data
    return out


def _seed_records(directory: Path, id_key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out[data.get(id_key, path.stem)] = data
    return out


def _targets(args: list[str]) -> list[Path]:
    if args:
        return [Path(a) for a in args]
    paths: list[Path] = []
    for pattern in DEFAULT_TARGETS:
        paths.extend(sorted(ROOT.glob(pattern)))
    return paths


def rewrite(path: Path, migration, field_schemas: dict, output_specs: dict, *, apply: bool) -> bool:
    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    updated = migration.embed_contract(payload, field_schemas, output_specs)
    new_text = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
    if updated == payload and json.loads(raw_text) == updated:
        return False
    if apply:
        path.write_text(new_text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="profile JSON files (default: the fixture folders)")
    parser.add_argument("--apply", action="store_true", help="write the rewritten files")
    parser.add_argument("--check", action="store_true", help="exit 1 when any file still needs the rewrite")
    parser.add_argument("--spec-json", action="append", default=[], help="id=path of an output spec JSON")
    parser.add_argument("--schema-json", action="append", default=[], help="id=path of a field schema JSON")
    args = parser.parse_args(argv)

    migration = load_migration()
    field_schemas = {**_seed_records(ROOT / "field_schemas", "schema_id"),
                     **_load_records(args.schema_json, "schema_id")}
    output_specs = {**_seed_records(ROOT / "output_specs", "spec_id"),
                    **_load_records(args.spec_json, "spec_id")}

    stale: list[Path] = []
    for path in _targets(args.paths):
        if not path.is_file():
            print(f"skip (missing): {path}")
            continue
        changed = rewrite(path, migration, field_schemas, output_specs, apply=args.apply)
        if changed:
            stale.append(path)
        label = "rewritten" if (changed and args.apply) else ("needs rewrite" if changed else "up to date")
        print(f"{label}: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    if args.check and stale:
        print(f"{len(stale)} profile file(s) still carry the legacy registry keys", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
