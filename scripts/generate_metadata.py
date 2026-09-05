#!/usr/bin/env python3
"""Add one model or runtime-asset bundle to the repository catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPOSITORY_ROOT / "catalog.yaml"
CATEGORY_KINDS = {
    "coperception": "coperception-checkpoint",
    "advcp": "advcp-assets",
}
VALID_BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GenerationError(RuntimeError):
    """Raised when a bundle cannot be added safely."""


class DuplicateArtifactError(GenerationError):
    """Raised when artifact content is already registered."""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed bundle path and source metadata.
    """
    parser = argparse.ArgumentParser(description="Generate metadata and register one new model or runtime asset bundle.")
    parser.add_argument("bundle", help="New bundle path relative to the repository, for example coperception/my-model.")
    parser.add_argument("--source-repository", required=True, help="Repository name written to source.repository.")
    parser.add_argument("--source-url", required=True, help="URL written to source.url.")
    parser.add_argument("--source-license", required=True, help="License identifier written to source.license.")
    return parser.parse_args()


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


def resolve_new_bundle(bundle_argument: str) -> tuple[str, Path]:
    """Resolve and validate a new bundle directory.

    Parameters
    ----------
    bundle_argument : str
        Absolute path or repository-relative bundle path.

    Returns
    -------
    tuple[str, pathlib.Path]
        Bundle category and resolved directory.

    Raises
    ------
    GenerationError
        If the path is outside the repository, has an unsupported layout, is
        missing, or already contains metadata.
    """
    requested_path = Path(bundle_argument).expanduser()
    bundle_root = (requested_path if requested_path.is_absolute() else REPOSITORY_ROOT / requested_path).resolve()
    try:
        relative_path = bundle_root.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise GenerationError(f'Bundle must be inside the repository: "{bundle_root}".') from error

    if len(relative_path.parts) != 2 or relative_path.parts[0] not in CATEGORY_KINDS:
        raise GenerationError('Bundle path must have the form "coperception/<id>" or "advcp/<id>".')
    if not VALID_BUNDLE_ID.fullmatch(relative_path.parts[1]):
        raise GenerationError(f'Invalid bundle ID: "{relative_path.parts[1]}".')
    if not bundle_root.is_dir():
        raise GenerationError(f'Bundle directory does not exist: "{bundle_root}".')
    if bundle_root.joinpath("meta.yaml").exists():
        raise GenerationError(f'Bundle "{relative_path.as_posix()}" already has metadata; only new bundles can be added.')
    return relative_path.parts[0], bundle_root


def collect_artifacts(bundle_root: Path) -> list[dict[str, str | int]]:
    """Build metadata records for every artifact in a bundle.

    Parameters
    ----------
    bundle_root : pathlib.Path
        Bundle directory to scan recursively.

    Returns
    -------
    list[dict[str, str | int]]
        Artifact paths, sizes, and SHA-256 digests.

    Raises
    ------
    GenerationError
        If the bundle is empty or contains a symbolic link.
    """
    artifacts: list[dict[str, str | int]] = []
    for path in sorted(bundle_root.rglob("*")):
        if path.is_file() and path.name != "meta.yaml":
            if path.is_symlink():
                raise GenerationError(f'Bundle artifacts must not be symbolic links: "{path}".')
            artifacts.append(
                {
                    "path": path.relative_to(bundle_root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    if not artifacts:
        raise GenerationError(f'Bundle "{bundle_root}" contains no artifacts.')
    return artifacts


def load_yaml_mapping(path: Path) -> dict[str, object]:
    """Load a YAML document and require a mapping at its root.

    Parameters
    ----------
    path : pathlib.Path
        YAML file to load.

    Returns
    -------
    dict[str, object]
        Parsed YAML mapping.

    Raises
    ------
    GenerationError
        If the file is unreadable, invalid, or does not contain a mapping.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise GenerationError(f'Cannot read valid YAML from "{path}": {error}') from error
    if not isinstance(document, dict):
        raise GenerationError(f'Expected a YAML mapping in "{path}".')
    return document


def existing_sha_index(catalog_entries: list[dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Index artifact digests from every catalog entry.

    Parameters
    ----------
    catalog_entries : list[dict[str, str]]
        Existing normalized catalog entries.

    Returns
    -------
    dict[str, list[tuple[str, str]]]
        Mapping from SHA-256 digest to bundle ID and artifact path pairs.

    Raises
    ------
    GenerationError
        If the checkout is incomplete or existing metadata is invalid.
    """
    index: dict[str, list[tuple[str, str]]] = {}
    for entry in catalog_entries:
        bundle_root = REPOSITORY_ROOT.joinpath(entry["path"]).resolve()
        try:
            bundle_root.relative_to(REPOSITORY_ROOT)
        except ValueError as error:
            raise GenerationError(f'Catalog bundle path escapes the repository: "{entry["path"]}".') from error
        metadata_path = bundle_root / "meta.yaml"
        if not metadata_path.is_file():
            raise GenerationError(f'Cannot perform a complete duplicate search because catalog metadata is missing: "{metadata_path}".')
        metadata = load_yaml_mapping(metadata_path)
        bundle_id = metadata.get("id")
        artifacts = metadata.get("artifacts")
        if not isinstance(bundle_id, str) or not isinstance(artifacts, list):
            raise GenerationError(f'Existing metadata is incomplete: "{metadata_path}".')
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str) or not isinstance(artifact.get("sha256"), str):
                raise GenerationError(f'Existing artifact metadata is invalid: "{metadata_path}".')
            index.setdefault(artifact["sha256"], []).append((bundle_id, artifact["path"]))
    return index


def reject_duplicate_artifacts(
    bundle_id: str,
    artifacts: list[dict[str, str | int]],
    catalog_entries: list[dict[str, str]],
) -> None:
    """Reject candidate artifacts already registered in another bundle.

    Parameters
    ----------
    bundle_id : str
        Candidate bundle ID.
    artifacts : list[dict[str, str | int]]
        Candidate artifact metadata.
    catalog_entries : list[dict[str, str]]
        Existing catalog entries used to build the digest index.

    Raises
    ------
    DuplicateArtifactError
        If any candidate SHA-256 digest already exists in the catalog.
    """
    sha_index = existing_sha_index(catalog_entries)
    conflicts: list[str] = []
    for artifact in artifacts:
        digest = str(artifact["sha256"])
        for existing_id, existing_path in sha_index.get(digest, []):
            conflicts.append(f"{bundle_id}/{artifact['path']} has SHA-256 {digest}, already registered as {existing_id}/{existing_path}")
    if conflicts:
        formatted_conflicts = "\n  - ".join(conflicts)
        raise DuplicateArtifactError(f"Duplicate artifact content found; no files were changed:\n  - {formatted_conflicts}")


def load_catalog_entries() -> list[dict[str, str]]:
    """Load and normalize the current bundle catalog.

    Returns
    -------
    list[dict[str, str]]
        Existing catalog entries.

    Raises
    ------
    GenerationError
        If the catalog schema or an entry is invalid.
    """
    catalog = load_yaml_mapping(CATALOG_PATH)
    bundles = catalog.get("bundles")
    if catalog.get("schema_version") != 1 or not isinstance(bundles, list):
        raise GenerationError(f'Unsupported or invalid catalog: "{CATALOG_PATH}".')

    entries: list[dict[str, str]] = []
    for entry in bundles:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(field), str) for field in ("id", "kind", "path")):
            raise GenerationError(f'Invalid bundle entry in "{CATALOG_PATH}".')
        entries.append({field: entry[field] for field in ("id", "kind", "path")})
    return entries


def add_catalog_entry(entries: list[dict[str, str]], *, bundle_id: str, kind: str, path: str) -> None:
    """Append a unique bundle entry to an in-memory catalog.

    Parameters
    ----------
    entries : list[dict[str, str]]
        Catalog entries to update.
    bundle_id : str
        Logical bundle ID.
    kind : str
        Metadata kind associated with the bundle category.
    path : str
        Repository-relative bundle path.

    Raises
    ------
    GenerationError
        If the bundle ID or path is already registered.
    """
    if any(entry["id"] == bundle_id for entry in entries):
        raise GenerationError(f'Bundle ID "{bundle_id}" is already present in the catalog.')
    if any(entry["path"] == path for entry in entries):
        raise GenerationError(f'Bundle path "{path}" is already present in the catalog.')
    entries.append({"id": bundle_id, "kind": kind, "path": path})


def render_artifacts(artifacts: list[dict[str, str | int]]) -> list[str]:
    """Render artifact records as YAML lines.

    Parameters
    ----------
    artifacts : list[dict[str, str | int]]
        Artifact records to render.

    Returns
    -------
    list[str]
        YAML lines for the ``artifacts`` sequence.
    """
    lines: list[str] = []
    for artifact in artifacts:
        lines.extend(
            [
                f"  - path: {json.dumps(artifact['path'], ensure_ascii=False)}",
                f"    size: {artifact['size']}",
                f"    sha256: {artifact['sha256']}",
            ]
        )
    return lines


def render_metadata(category: str, bundle_id: str, source: dict[str, str], artifacts: list[dict[str, str | int]]) -> str:
    """Render metadata for one bundle.

    Parameters
    ----------
    category : str
        Bundle category from :data:`CATEGORY_KINDS`.
    bundle_id : str
        Logical bundle ID.
    source : dict[str, str]
        Source repository, URL, and license.
    artifacts : list[dict[str, str | int]]
        Artifact records included in the bundle.

    Returns
    -------
    str
        Complete ``meta.yaml`` document.
    """
    lines = [
        "schema_version: 1",
        f"id: {bundle_id}",
        f"kind: {CATEGORY_KINDS[category]}",
        "version: 1",
    ]
    if category == "coperception":
        dataset = "v2xsim" if "v2xsim" in bundle_id.lower() else "opv2v"
        fusion = next((name for name in ("early", "late", "intermediate") if name in bundle_id.lower()), "unknown")
        lines.extend(
            [
                "compatibility:",
                "  framework: OpenCOOD",
                f"  dataset: {dataset}",
                f"  fusion: {fusion}",
                f"  requires_custom_cuda: {'true' if bundle_id.lower().startswith('fpvrcnn-') else 'false'}",
            ]
        )
    lines.extend(
        [
            "source:",
            f"  repository: {json.dumps(source['repository'], ensure_ascii=False)}",
            f"  url: {json.dumps(source['url'], ensure_ascii=False)}",
            f"  license: {json.dumps(source['license'], ensure_ascii=False)}",
            "artifacts:",
        ]
    )
    lines.extend(render_artifacts(artifacts))
    return "\n".join(lines) + "\n"


def render_catalog(entries: list[dict[str, str]]) -> str:
    """Render sorted catalog entries as YAML.

    Parameters
    ----------
    entries : list[dict[str, str]]
        Catalog entries to render.

    Returns
    -------
    str
        Complete catalog document.
    """
    lines = ["schema_version: 1", "bundles:"]
    for entry in sorted(entries, key=lambda item: item["path"]):
        lines.extend(
            [
                f"  - id: {entry['id']}",
                f"    kind: {entry['kind']}",
                f"    path: {entry['path']}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_new_bundle(metadata_path: Path, metadata: str, catalog: str) -> None:
    """Commit new metadata and catalog content with temporary files.

    Parameters
    ----------
    metadata_path : pathlib.Path
        Destination for the new bundle metadata.
    metadata : str
        Rendered metadata document.
    catalog : str
        Rendered catalog document.

    Raises
    ------
    OSError
        If either document cannot be written or installed.
    """
    metadata_temporary = metadata_path.with_suffix(".yaml.tmp")
    catalog_temporary = CATALOG_PATH.with_suffix(".yaml.tmp")
    metadata_committed = False
    try:
        metadata_temporary.write_text(metadata, encoding="utf-8")
        catalog_temporary.write_text(catalog, encoding="utf-8")
        os.replace(metadata_temporary, metadata_path)
        metadata_committed = True
        os.replace(catalog_temporary, CATALOG_PATH)
    except OSError:
        if metadata_committed:
            metadata_path.unlink(missing_ok=True)
        raise
    finally:
        metadata_temporary.unlink(missing_ok=True)
        catalog_temporary.unlink(missing_ok=True)


def main() -> int:
    """Run the incremental bundle registration command.

    Returns
    -------
    int
        Zero on success and one when preflight or writing fails.
    """
    args = parse_args()
    try:
        source = {
            "repository": args.source_repository,
            "url": args.source_url,
            "license": args.source_license,
        }
        if any(not value.strip() for value in source.values()):
            raise GenerationError("Source repository, URL, and license must be non-empty strings.")

        category, bundle_root = resolve_new_bundle(args.bundle)
        bundle_id = bundle_root.name
        artifacts = collect_artifacts(bundle_root)

        entries = load_catalog_entries()
        reject_duplicate_artifacts(bundle_id, artifacts, entries)
        relative_path = bundle_root.relative_to(REPOSITORY_ROOT).as_posix()
        add_catalog_entry(entries, bundle_id=bundle_id, kind=CATEGORY_KINDS[category], path=relative_path)

        metadata = render_metadata(category, bundle_id, source, artifacts)
        write_new_bundle(bundle_root / "meta.yaml", metadata, render_catalog(entries))
    except DuplicateArtifactError as error:
        print(f"Warning: {error}", file=sys.stderr)
        return 1
    except (GenerationError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f'Added bundle "{relative_path}" to the catalog.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
