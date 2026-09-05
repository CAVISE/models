#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate metadata and artifacts in every model bundle.")
    parser.add_argument("--source-repository", required=True, help="Expected source.repository value.")
    parser.add_argument("--source-url", required=True, help="Expected source.url value.")
    parser.add_argument("--source-license", required=True, help="Expected source.license value.")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_bundle(bundle_root: Path, expected_source: dict[str, str]) -> list[str]:
    errors: list[str] = []
    metadata_path = bundle_root / "meta.yaml"
    try:
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [f"{metadata_path}: {error}"]

    if not isinstance(metadata, dict):
        return [f"{metadata_path}: metadata must be a mapping"]
    if metadata.get("id") != bundle_root.name:
        errors.append(f"{metadata_path}: id does not match directory name")
    if metadata.get("source") != expected_source:
        errors.append(f"{metadata_path}: source does not match the expected repository, URL, and license")

    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return errors + [f"{metadata_path}: artifacts must be a non-empty list"]

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append(f"{metadata_path}: invalid artifact entry")
            continue
        relative_path = artifact.get("path")
        if not isinstance(relative_path, str):
            errors.append(f"{metadata_path}: artifact path must be a string")
            continue
        path = bundle_root / relative_path
        if not path.is_file():
            errors.append(f"{metadata_path}: missing artifact {relative_path}")
            continue
        if path.stat().st_size != artifact.get("size"):
            errors.append(f"{metadata_path}: size mismatch for {relative_path}")
        if sha256(path) != artifact.get("sha256"):
            errors.append(f"{metadata_path}: SHA-256 mismatch for {relative_path}")
    return errors


def main() -> int:
    args = parse_args()
    expected_source = {
        "repository": args.source_repository,
        "url": args.source_url,
        "license": args.source_license,
    }
    errors: list[str] = []
    for category in ("coperception", "advcp"):
        for bundle_root in sorted(REPOSITORY_ROOT.joinpath(category).iterdir()):
            if bundle_root.is_dir():
                errors.extend(validate_bundle(bundle_root, expected_source))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("All model metadata is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
