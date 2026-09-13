# EmuCoreR Texture Catalog

Curated PlayStation 1 texture-pack catalog consumed by the EmuCoreR texture
manager.

The Git history contains metadata only. Texture archives stay in the original
author's GitHub Releases or, when redistribution is explicitly allowed, in this
repository's Releases. Git LFS must not be used: catalogs, archives and release
assets are plain files.

## Files

- `textures.json` - production catalog used by EmuCoreR.
- `catalog-audit.json` - persistent source and content fingerprints for
  published batches and duplicate prevention.
- `schemas/texture-catalog.schema.json` - public format contract.
- `scripts/validate_catalog.py` - dependency-free validation.
- `scripts/prepare_pack.py` - safe normalization, inspection and comparison.
- `scripts/split_pack.py` - deterministic binary splitting for normalized ZIPs
  that exceed GitHub's per-asset limit.
- `scripts/safe_extract_7z.py` - guarded integrity testing and extraction of
  public 7z sources.
- `scripts/register_batch.py` - atomic configurable-size catalog and audit
  registration.

## Texture format

The bundled SwanStation (DuckStation) core loads replacement textures named
`vram-write-<32 hex chars>.<png|jpg|tga|bmp>` recursively under
`<textures root>/<SERIAL>/`. There is no `replacements/` folder concept on PS1.

Normalized release archives therefore contain only `vram-write-*` files with
archive-root relative paths. Subfolders are allowed and preserved, but serial
folders, `textures/`, `replacements/` and GitHub codeload wrapper roots
(`<name>-<40 hex>`) are stripped during normalization.

GitHub Releases for this catalog are tagged `texture-catalog-2026-09-13` and
all downloadable assets live in this repository's Releases.

## Catalog fields

Every `textures.json` entry records its immutable identity and provenance:
`id`, `name`, `gameTitle`, `serials` (`XXXX-#####`), `version`, `authors`,
`credits`, `description`, `downloadUrl`, `sourceUrl`, `license`, `sizeBytes`,
`sha256` (64 hexadecimal characters), `fileCount`, and `previewUrls`. Multipart
packs additionally list `parts` (minimum two), each with `downloadUrl`,
`sizeBytes` and `sha256`; the parts sizes must sum to `sizeBytes` and only the
first part URL may equal `downloadUrl`.

## Limits

The app and the tooling enforce the same limits:

- 50,000 texture files per pack;
- 512 MiB per texture file;
- 12 GiB total uncompressed;
- 16 GiB per final ZIP;
- 2 GiB per release asset (split parts are 1,900,000,000 bytes);
- 8 MiB per catalog file.

## Copyright and mirroring

Only mirror a texture pack when its license or the author's explicit permission
allows redistribution. Otherwise the catalog links to the author's original
archive and does not host a copy. Never re-upload someone else's work without
permission.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a pack.
