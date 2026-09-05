#!/usr/bin/env python3
"""Validate bundle metadata, artifacts, and catalog consistency."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATEGORY_KINDS = {
    "coperception": "coperception-checkpoint",
    "advcp": "advcp-assets",
}


def sha256(path: Path) -> str:
    """Calculate a file's SHA-256 digest.

    Parameters
    ----------
    path : pathlib.Path
        File to hash.

    Returns
    -------
    str
        Lowercase hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_bundle(bundle_root: Path, expected_kind: str) -> list[str]:
    """Validate one bundle and all artifacts declared by its metadata.

    Parameters
    ----------
    bundle_root : pathlib.Path
        Bundle directory containing ``meta.yaml``.
    expected_kind : str
        Metadata kind required for the bundle's category.

    Returns
    -------
    list[str]
        Validation errors, or an empty list for a valid bundle.
    """
    errors: list[str] = []
    metadata_path = bundle_root / "meta.yaml"
    try:
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [f"{metadata_path}: {error}"]

    if not isinstance(metadata, dict):
        return [f"{metadata_path}: metadata must be a mapping"]
    if metadata.get("schema_version") != 1:
        errors.append(f"{metadata_path}: unsupported schema version")
    if metadata.get("id") != bundle_root.name:
        errors.append(f"{metadata_path}: id does not match directory name")
    if metadata.get("kind") != expected_kind:
        errors.append(f"{metadata_path}: kind does not match bundle category")
    source = metadata.get("source")
    if not isinstance(source, dict) or not all(
        isinstance(source.get(field), str) and source[field].strip() for field in ("repository", "url", "license")
    ):
        errors.append(f"{metadata_path}: source repository, URL, and license must be non-empty strings")

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


def validate_catalog(expected_entries: set[tuple[str, str, str]]) -> list[str]:
    """Compare the catalog with bundle directories in the checkout.

    Parameters
    ----------
    expected_entries : set[tuple[str, str, str]]
        Bundle ID, kind, and path tuples discovered from the filesystem.

    Returns
    -------
    list[str]
        Catalog validation errors, or an empty list when it is consistent.
    """
    catalog_path = REPOSITORY_ROOT / "catalog.yaml"
    try:
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [f"{catalog_path}: {error}"]
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        return [f"{catalog_path}: catalog must use schema version 1"]

    bundles = catalog.get("bundles")
    if not isinstance(bundles, list):
        return [f"{catalog_path}: bundles must be a list"]

    errors: list[str] = []
    actual_entries: list[tuple[str, str, str]] = []
    for entry in bundles:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(field), str) for field in ("id", "kind", "path")):
            errors.append(f"{catalog_path}: invalid bundle entry")
            continue
        actual_entries.append((entry["id"], entry["kind"], entry["path"]))

    actual_entry_set = set(actual_entries)
    if len(actual_entries) != len(actual_entry_set):
        errors.append(f"{catalog_path}: duplicate bundle entries")
    for entry in sorted(expected_entries - actual_entry_set):
        errors.append(f"{catalog_path}: missing bundle entry {entry}")
    for entry in sorted(actual_entry_set - expected_entries):
        errors.append(f"{catalog_path}: unexpected bundle entry {entry}")
    return errors


def main() -> int:
    """Validate the complete repository.

    Returns
    -------
    int
        Zero when all checks pass and one when validation errors are found.
    """
    errors: list[str] = []
    expected_entries: set[tuple[str, str, str]] = set()
    for category, kind in CATEGORY_KINDS.items():
        for bundle_root in sorted(REPOSITORY_ROOT.joinpath(category).iterdir()):
            if bundle_root.is_dir():
                errors.extend(validate_bundle(bundle_root, kind))
                expected_entries.add((bundle_root.name, kind, bundle_root.relative_to(REPOSITORY_ROOT).as_posix()))
    errors.extend(validate_catalog(expected_entries))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("All model metadata is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
