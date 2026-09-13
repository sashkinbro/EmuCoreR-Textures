#!/usr/bin/env python3
from __future__ import annotations

import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from prepare_pack import PackError, compare, prepare, validate

VRAM_A = "vram-write-" + "a" * 32
VRAM_B = "vram-write-" + "b" * 32
VRAM_C = "vram-write-" + "c" * 32
VRAM_D = "vram-write-" + "d" * 32


def png(width: int = 2, height: int = 3) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    raw = b"\x00" + (b"\x00\x00\x00\xff" * width)
    idat_data = zlib.compress(raw * height)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data
    idat += struct.pack(">I", zlib.crc32(b"IDAT" + idat_data))
    iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return signature + ihdr + idat + iend


def jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 28


def bmp() -> bytes:
    return b"BM" + b"\x00" * 30


def tga() -> bytes:
    return b"\x00\x00\x02" + b"\x00" * 29


class PreparePackTest(unittest.TestCase):
    def test_normalizes_serial_textures_and_replacements_roots(self) -> None:
        cases = (
            f"wrapper/SLUS-12345/textures/ui/{VRAM_A}.png",
            f"wrapper/SLUS-12345/replacements/ui/{VRAM_A}.png",
            f"textures/SLUS-12345/ui/{VRAM_A}.png",
            f"replacements/SLUS-12345/ui/{VRAM_A}.png",
        )
        for source_name in cases:
            with self.subTest(source_name=source_name):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    source = root / "source.zip"
                    output = root / "output.zip"
                    with zipfile.ZipFile(source, "w") as archive:
                        archive.writestr(source_name, png())
                        archive.writestr("notes.txt", "not shipped")

                    summary = prepare(source, output, strip_components=0)

                    self.assertEqual(summary.fileCount, 1)
                    self.assertEqual(summary.skippedFiles, 1)
                    with zipfile.ZipFile(output) as archive:
                        self.assertEqual(
                            [entry.filename for entry in archive.infolist()],
                            [f"ui/{VRAM_A}.png"],
                        )
                    validated = validate(output)
                    self.assertEqual(validated.fileCount, summary.fileCount)
                    self.assertEqual(validated.manifestSha256, summary.manifestSha256)
                    self.assertEqual(validated.contentSetSha256, summary.contentSetSha256)
                    self.assertEqual(validated.skippedFiles, 0)

    def test_strips_github_codeload_wrapper_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            wrapper = "EmuCoreR-Textures-0123456789abcdef0123456789abcdef01234567"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"{wrapper}/ui/{VRAM_A}.png", png())

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    [f"ui/{VRAM_A}.png"],
                )

    def test_keeps_nested_subfolders_after_serial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-00594/ui/fonts/{VRAM_A}.png", png())

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    [f"ui/fonts/{VRAM_A}.png"],
                )

    def test_accepts_jpeg_bmp_and_tga_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-12345/textures/{VRAM_A}.png", png())
                archive.writestr(f"SLUS-12345/textures/{VRAM_B}.jpg", jpeg())
                archive.writestr(f"SLUS-12345/textures/{VRAM_C}.bmp", bmp())
                archive.writestr(f"SLUS-12345/textures/{VRAM_D}.tga", tga())

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 4)
            self.assertEqual(
                summary.extensions, {"bmp": 1, "jpg": 1, "png": 1, "tga": 1}
            )

    def test_accepts_case_insensitive_vram_write_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    f"SLUS-12345/textures/{VRAM_A.upper()}.PNG", png()
                )

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)

    def test_skips_files_that_are_not_vram_write_textures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-12345/textures/{VRAM_A}.png", png())
                archive.writestr("SLUS-12345/textures/foo.png", png())
                archive.writestr("notes.txt", "not shipped")

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)
            self.assertEqual(summary.skippedFiles, 2)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    [f"{VRAM_A}.png"],
                )

    def test_rejects_pack_without_vram_write_textures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("SLUS-12345/textures/foo.png", png())
                archive.writestr("notes.txt", "not shipped")

            with self.assertRaises(PackError) as raised:
                prepare(source, root / "output.zip", strip_components=0)

            self.assertIn("no compatible vram-write textures", str(raised.exception))

    def test_rejects_duplicate_normalized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-12345/textures/ui/{VRAM_A}.png", png())
                archive.writestr(f"textures/UI/{VRAM_A.upper()}.PNG", png())

            with self.assertRaises(PackError):
                prepare(source, root / "output.zip", strip_components=0)

    def test_rejects_invalid_texture_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-12345/textures/{VRAM_A}.png", b"not a png")

            with self.assertRaises(PackError):
                prepare(source, root / "output.zip", strip_components=0)

    def test_validate_rejects_non_vram_write_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "archive.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("ui/foo.png", png())

            with self.assertRaises(PackError) as raised:
                validate(archive_path)

            self.assertIn("entry is not a vram-write texture", str(raised.exception))

    def test_strip_components_applies_after_root_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"pack/ui/{VRAM_A}.png", png())

            summary = prepare(source, output, strip_components=2)

            self.assertEqual(summary.fileCount, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    [f"{VRAM_A}.png"],
                )

    def test_rejects_strip_components_that_remove_the_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(f"SLUS-12345/{VRAM_A}.png", png())

            with self.assertRaises(PackError):
                prepare(source, root / "output.zip", strip_components=1)

    def test_compare_detects_repacked_duplicate_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            left = root / "left.zip"
            right = root / "right.zip"
            with zipfile.ZipFile(left, "w") as archive:
                archive.writestr(f"ui/{VRAM_A}.png", png())
            with zipfile.ZipFile(right, "w") as archive:
                archive.writestr(f"renamed/{VRAM_A}.png", png())

            result = compare(left, right)

            self.assertFalse(result.exactManifestMatch)
            self.assertTrue(result.exactContentSetMatch)
            self.assertEqual(result.sharedFileContents, 1)


if __name__ == "__main__":
    unittest.main()
