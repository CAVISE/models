# CAVISE models and runtime assets

This repository contains versioned model bundles and other large runtime
assets used by CAVISE. Git LFS is intentionally not used.

Each bundle is immutable and contains a `meta.yaml` file with its logical ID,
kind, compatibility information, artifact sizes, and SHA-256 checksums. Add a
new bundle ID instead of replacing a binary in an existing bundle.

The repository layout is:

```text
coperception/<model-id>/
advcp/<asset-bundle-id>/
```

OpenCDA can fetch a single bundle with a partial sparse checkout, so a user
does not need to download every checkpoint. Metadata can be regenerated and
validated with:

```bash
python scripts/generate_metadata.py
python scripts/validate_metadata.py
```

Before publishing a bundle, replace `REVIEW_REQUIRED` in its metadata with the
verified artifact license and fill in the original source URL when known.
