#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate metadata for every model and runtime asset bundle.")
    parser.add_argument("--source-repository", required=True, help="Repository name written to source.repository.")
    parser.add_argument("--source-url", required=True, help="URL written to source.url.")
    parser.add_argument("--source-license", required=True, help="License identifier written to source.license.")
    return parser.parse_args()


def artifact_metadata(path: Path, bundle_root: Path) -> list[str]:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)

    return [
        f"  - path: {path.relative_to(bundle_root).as_posix()}",
        f"    size: {path.stat().st_size}",
        f"    sha256: {digest.hexdigest()}",
    ]


def write_coperception_metadata(bundle_root: Path, source: dict[str, str]) -> None:
    bundle_id = bundle_root.name
    dataset = "v2xsim" if "v2xsim" in bundle_id.lower() else "opv2v"
    fusion = next((name for name in ("early", "late", "intermediate") if name in bundle_id.lower()), "unknown")
    artifacts = sorted(path for path in bundle_root.iterdir() if path.is_file() and path.name != "meta.yaml")

    lines = [
        "schema_version: 1",
        f"id: {bundle_id}",
        "kind: coperception-checkpoint",
        "version: 1",
        "compatibility:",
        "  framework: OpenCOOD",
        f"  dataset: {dataset}",
        f"  fusion: {fusion}",
        f"  requires_custom_cuda: {'true' if bundle_id.lower().startswith('fpvrcnn-') else 'false'}",
        "source:",
        f"  repository: {source['repository']}",
        f"  url: {source['url']}",
        f"  license: {source['license']}",
        "artifacts:",
    ]
    for artifact in artifacts:
        lines.extend(artifact_metadata(artifact, bundle_root))
    bundle_root.joinpath("meta.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_advcp_metadata(bundle_root: Path, source: dict[str, str]) -> None:
    artifacts = sorted(path for path in bundle_root.rglob("*") if path.is_file() and path.name != "meta.yaml")
    lines = [
        "schema_version: 1",
        f"id: {bundle_root.name}",
        "kind: advcp-assets",
        "version: 1",
        "source:",
        f"  repository: {source['repository']}",
        f"  url: {source['url']}",
        f"  license: {source['license']}",
        "artifacts:",
    ]
    for artifact in artifacts:
        lines.extend(artifact_metadata(artifact, bundle_root))
    bundle_root.joinpath("meta.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_catalog(bundle_paths: list[tuple[str, Path]]) -> None:
    lines = ["schema_version: 1", "bundles:"]
    for kind, bundle_path in sorted(bundle_paths, key=lambda item: item[1].as_posix()):
        lines.extend(
            [
                f"  - id: {bundle_path.name}",
                f"    kind: {kind}",
                f"    path: {bundle_path.relative_to(REPOSITORY_ROOT).as_posix()}",
            ]
        )
    REPOSITORY_ROOT.joinpath("catalog.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source = {
        "repository": args.source_repository,
        "url": args.source_url,
        "license": args.source_license,
    }
    bundles: list[tuple[str, Path]] = []
    for bundle_root in sorted(REPOSITORY_ROOT.joinpath("coperception").iterdir()):
        if bundle_root.is_dir():
            write_coperception_metadata(bundle_root, source)
            bundles.append(("coperception-checkpoint", bundle_root))

    for bundle_root in sorted(REPOSITORY_ROOT.joinpath("advcp").iterdir()):
        if bundle_root.is_dir():
            write_advcp_metadata(bundle_root, source)
            bundles.append(("advcp-assets", bundle_root))

    write_catalog(bundles)


if __name__ == "__main__":
    main()
