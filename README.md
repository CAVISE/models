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
python scripts/validate_metadata.py
```

The same validation runs automatically as part of pre-commit:

```bash
pre-commit run --all-files
```

To add a bundle, first place its files into a new directory directly under
`coperception/` or `advcp/`. Then pass that directory and its source information
to the generator:

```bash
python scripts/generate_metadata.py coperception/my-model \
  --source-repository CAVISE/OpenCDA \
  --source-url https://github.com/CAVISE/OpenCDA \
  --source-license MIT
```

The generator creates only that bundle's `meta.yaml` and appends one sorted
entry to `catalog.yaml`; existing bundle metadata is never regenerated. Before
writing anything, it compares every new artifact's SHA-256 against all existing
metadata. If the same content is already registered under another bundle ID,
the command aborts and reports both locations.

Run the generator from a complete checkout. If metadata for any bundle listed
in `catalog.yaml` is missing locally, the command aborts rather than performing
an incomplete duplicate search.

All three source arguments are required. For a bundle imported from another
repository, provide that repository's values:

```bash
python scripts/generate_metadata.py advcp/example-assets \
  --source-repository example/models \
  --source-url https://github.com/example/models \
  --source-license Apache-2.0
```

Use `--help` with either script to see all available options.

All current bundles originate from the CAVISE OpenCDA repository and are
published under the MIT license, as recorded in each `meta.yaml` file.
