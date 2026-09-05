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
does not need to download every checkpoint.

## Metadata tools

Install the dependency used by the metadata validator:

```bash
python -m pip install -r requirements.txt
```

Run the validator after adding or changing a bundle. It verifies every
artifact's presence, size, and SHA-256 checksum, as well as the bundle source
fields:

```bash
python scripts/validate_metadata.py \
  --source-repository CAVISE/OpenCDA \
  --source-url https://github.com/CAVISE/OpenCDA \
  --source-license MIT
```

The same validation runs automatically as part of pre-commit:

```bash
pre-commit run --all-files
```

To regenerate all `meta.yaml` files and `catalog.yaml`, run:

```bash
python scripts/generate_metadata.py \
  --source-repository CAVISE/OpenCDA \
  --source-url https://github.com/CAVISE/OpenCDA \
  --source-license MIT
```

Generation overwrites existing bundle metadata. All three source arguments
are required by both scripts. Pass matching values to the validator after
importing bundles from a different source:

```bash
python scripts/generate_metadata.py \
  --source-repository example/models \
  --source-url https://github.com/example/models \
  --source-license Apache-2.0

python scripts/validate_metadata.py \
  --source-repository example/models \
  --source-url https://github.com/example/models \
  --source-license Apache-2.0
```

Use `--help` with either script to see all available options.

All current bundles originate from the CAVISE OpenCDA repository and are
published under the MIT license, as recorded in each `meta.yaml` file.
