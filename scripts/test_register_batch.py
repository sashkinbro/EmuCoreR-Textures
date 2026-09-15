import argparse
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import register_batch
from register_batch import (
    DEFAULT_REPOSITORY,
    RegistrationError,
    build_parser,
    provenance_keys,
    resolve_source_sha256,
    sha256_file,
)


def write_normalized_pack(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("vram-write-" + "a" * 32 + ".bmp", b"BM" + b"\x00" * 30)


class ProvenanceKeyTests(unittest.TestCase):
    def test_normalizes_url_serial_and_author_case(self):
        left = provenance_keys(
            "HTTPS://EXAMPLE.COM/PACK",
            ["slus-20062"],
            ["FunnyNameXYZ"],
        )
        right = provenance_keys(
            "https://example.com/pack",
            ["SLUS-20062"],
            ["funnynamexyz"],
        )
        self.assertEqual(left, right)

    def test_different_author_or_serial_does_not_overlap(self):
        original = provenance_keys(
            "https://example.com/thread",
            ["SLUS-20062"],
            ["Author A"],
        )
        other_author = provenance_keys(
            "https://example.com/thread",
            ["SLUS-20062"],
            ["Author B"],
        )
        other_serial = provenance_keys(
            "https://example.com/thread",
            ["SLUS-21590"],
            ["Author A"],
        )
        self.assertFalse(original & other_author)
        self.assertFalse(original & other_serial)

    def test_rejects_invalid_serial_list(self):
        with self.assertRaises(RegistrationError):
            provenance_keys("https://example.com/thread", [], ["Author"])


class SourceEvidenceTests(unittest.TestCase):
    def test_uses_verified_digest_when_streamed_source_was_removed(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "streamed-source.7z"
            digest = "A" * 64
            self.assertEqual(resolve_source_sha256(missing, 123, digest), digest)

    def test_checks_declared_digest_when_source_is_present(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.zip"
            source.write_bytes(b"verified source")
            digest = sha256_file(source)
            self.assertEqual(
                resolve_source_sha256(source, source.stat().st_size, digest),
                digest,
            )
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(source, source.stat().st_size, "0" * 64)

    def test_missing_source_requires_a_valid_digest(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.zip"
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(missing, 123, None)
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(missing, 123, "not-a-digest")


def write_normalized_pack_variant(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "vram-write-" + marker * 32 + ".bmp",
            b"BM" + b"\x00" * 30 + marker.encode("ascii"),
        )


class SourceSplitTests(unittest.TestCase):
    def build_args(self, root: Path, manifest: list[dict]) -> argparse.Namespace:
        source_dir = root / "source"
        ready_dir = root / "ready"
        source_dir.mkdir()
        ready_dir.mkdir()
        source_file = source_dir / "source.zip"
        source_file.write_bytes(b"verified source")
        digest = sha256_file(source_file)
        write_normalized_pack_variant(ready_dir / "pack-a.zip", "a")
        write_normalized_pack_variant(ready_dir / "pack-b.zip", "b")
        for item in manifest:
            item["sourceSha256"] = digest
            item["expectedSourceBytes"] = source_file.stat().st_size
        catalog_path = root / "textures.json"
        catalog_path.write_text(
            json.dumps({"schemaVersion": 1, "generatedAt": "2026-09-01T00:00:00Z", "entries": []}),
            encoding="utf-8",
        )
        audit_path = root / "catalog-audit.json"
        audit_path.write_text(
            json.dumps({"schemaVersion": 1, "batches": []}), encoding="utf-8"
        )
        manifest_path = root / "sources.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return argparse.Namespace(
            manifest=manifest_path,
            source_dir=source_dir,
            ready_dir=ready_dir,
            validation_log_dir=None,
            catalog=catalog_path,
            audit=audit_path,
            repository=DEFAULT_REPOSITORY,
            release_tag="texture-catalog-2026-09-13",
            batch_id="2026-09-13-001",
            verified_at="2026-09-13T00:00:00Z",
            expected_count=len(manifest),
            write=False,
        )

    @staticmethod
    def entry(slug: str, asset: str, source_split: dict | None = None) -> dict:
        item = {
            "slug": slug,
            "sourceFile": "source.zip",
            "assetName": asset,
            "catalog": {
                "id": slug,
                "name": slug,
                "gameTitle": slug,
                "serials": ["SLUS-00594"],
                "version": "1.0",
                "authors": ["Test Author"],
                "credits": "Test credits",
                "description": "Test description",
                "sourceUrl": "https://example.com/source",
                "license": "CC0",
            },
        }
        if source_split is not None:
            item["sourceSplit"] = source_split
        return item

    def test_shared_source_requires_source_split(self):
        with TemporaryDirectory() as directory:
            args = self.build_args(
                Path(directory),
                [self.entry("pack-a", "pack-a.zip"), self.entry("pack-b", "pack-b.zip")],
            )
            with self.assertRaises(RegistrationError):
                register_batch.register(args)

    def test_shared_source_with_complete_parts_registers(self):
        with TemporaryDirectory() as directory:
            args = self.build_args(
                Path(directory),
                [
                    self.entry("pack-a", "pack-a.zip", {"part": 1, "total": 2}),
                    self.entry("pack-b", "pack-b.zip", {"part": 2, "total": 2}),
                ],
            )
            catalog, audit = register_batch.register(args)
            self.assertEqual(len(catalog["entries"]), 2)
            self.assertEqual(
                audit["batches"][0]["entries"][0]["sourceSplit"],
                {"part": 1, "total": 2},
            )

    def test_shared_source_with_incomplete_parts_is_rejected(self):
        with TemporaryDirectory() as directory:
            args = self.build_args(
                Path(directory),
                [
                    self.entry("pack-a", "pack-a.zip", {"part": 1, "total": 3}),
                    self.entry("pack-b", "pack-b.zip", {"part": 2, "total": 3}),
                ],
            )
            with self.assertRaises(RegistrationError):
                register_batch.register(args)


class RepositoryUrlTests(unittest.TestCase):
    def test_default_repository_targets_emucorer(self):
        self.assertEqual(DEFAULT_REPOSITORY, "sashkinbro/EmuCoreR-Textures")

    def test_cli_defaults_to_emucorer_repository(self):
        args = build_parser().parse_args(
            [
                "--manifest",
                "sources.json",
                "--source-dir",
                "source",
                "--ready-dir",
                "ready",
                "--release-tag",
                "texture-catalog-2026-09-13",
                "--batch-id",
                "2026-09-13-001",
                "--verified-at",
                "2026-09-13T00:00:00Z",
            ]
        )
        self.assertEqual(args.repository, "sashkinbro/EmuCoreR-Textures")

    def test_registration_builds_emucorer_download_urls(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            ready_dir = root / "ready"
            source_dir.mkdir()
            ready_dir.mkdir()
            source_file = source_dir / "source.zip"
            source_file.write_bytes(b"verified source")
            archive = ready_dir / "pack.zip"
            write_normalized_pack(archive)
            catalog_path = root / "textures.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "generatedAt": "2026-09-01T00:00:00Z",
                        "entries": [],
                    }
                ),
                encoding="utf-8",
            )
            audit_path = root / "catalog-audit.json"
            audit_path.write_text(
                json.dumps({"schemaVersion": 1, "batches": []}),
                encoding="utf-8",
            )
            manifest_path = root / "sources.json"
            manifest_path.write_text(
                json.dumps(
                    [
                        {
                            "slug": "test-pack",
                            "sourceFile": "source.zip",
                            "assetName": "pack.zip",
                            "expectedSourceBytes": source_file.stat().st_size,
                            "sourceSha256": sha256_file(source_file),
                            "catalog": {
                                "id": "test-pack",
                                "name": "Test Pack",
                                "gameTitle": "Test Game",
                                "serials": ["SLUS-00594"],
                                "version": "1.0",
                                "authors": ["Test Author"],
                                "credits": "Test credits",
                                "description": "Test description",
                                "sourceUrl": "https://example.com/source",
                                "license": "CC0",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                manifest=manifest_path,
                source_dir=source_dir,
                ready_dir=ready_dir,
                validation_log_dir=None,
                catalog=catalog_path,
                audit=audit_path,
                repository=DEFAULT_REPOSITORY,
                release_tag="texture-catalog-2026-09-13",
                batch_id="2026-09-13-001",
                verified_at="2026-09-13T00:00:00Z",
                expected_count=1,
                write=False,
            )

            catalog, audit = register_batch.register(args)

            self.assertEqual(
                catalog["entries"][0]["downloadUrl"],
                "https://github.com/sashkinbro/EmuCoreR-Textures/releases/download/"
                "texture-catalog-2026-09-13/pack.zip",
            )
            self.assertEqual(
                audit["batches"][0]["releaseTag"], "texture-catalog-2026-09-13"
            )


if __name__ == "__main__":
    unittest.main()
