import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codec_transit.cli import publish


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "in.txt"
        self.output = self.root / "out.txt"

    def invoke(self, raw, *args):
        self.source.write_bytes(raw)
        process = subprocess.run(
            [sys.executable, "-m", "codec_transit", str(self.source), *args],
            capture_output=True,
            text=True,
        )
        self.assertNotIn("Traceback", process.stderr)
        return process, json.loads(process.stdout)

    def test_actual_conversion(self):
        raw = "€ café\r\n".encode("cp1252")
        process, report = self.invoke(
            raw, "--from", "cp1252", "--to", "utf8", "--output", str(self.output)
        )
        self.assertEqual(process.returncode, 0)
        self.assertTrue(report["output_written"])
        self.assertEqual(self.output.read_bytes(), "€ café\r\n".encode())
        self.assertEqual(self.source.read_bytes(), raw)

    def test_changed_unicode_never_published(self):
        process, report = self.invoke(
            "〜".encode(), "--from", "utf8", "--to", "cp932", "--output", str(self.output)
        )
        self.assertEqual(process.returncode, 1)
        self.assertFalse(self.output.exists())
        self.assertFalse(report["output_written"])

    def test_unencodable_never_published(self):
        process, report = self.invoke(
            "PRIVATE中文".encode(), "--from", "utf8", "--to", "ascii", "--output", str(self.output)
        )
        self.assertEqual(process.returncode, 1)
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertFalse(self.output.exists())

    def test_output_exists(self):
        self.output.write_bytes(b"KEEP")
        process, _ = self.invoke(
            b"abc", "--from", "ascii", "--to", "utf8", "--output", str(self.output)
        )
        self.assertEqual(process.returncode, 2)
        self.assertEqual(self.output.read_bytes(), b"KEEP")

    def test_invalid_source(self):
        process, report = self.invoke(b"\xff", "--from", "utf8", "--to", "utf8")
        self.assertEqual(process.returncode, 2)
        self.assertEqual(report["error"]["code"], "source_decode_error")

    def test_unsupported_and_duplicate_aliases(self):
        for extra in (("--to", "base64_codec"), ("--to", "ascii", "--to", "us-ascii")):
            process, _ = self.invoke(b"abc", "--from", "ascii", *extra)
            self.assertEqual(process.returncode, 2)

    def test_input_limit(self):
        process, report = self.invoke(
            b"abcd", "--from", "ascii", "--to", "utf8", "--max-bytes", "3"
        )
        self.assertEqual(process.returncode, 2)
        self.assertEqual(report["error"]["code"], "input_byte_limit")

    def test_source_byte_gate(self):
        process, report = self.invoke(
            bytes.fromhex("fbfc"),
            "--from",
            "cp932",
            "--to",
            "utf8",
            "--require-byte-roundtrip",
            "--output",
            str(self.output),
        )
        self.assertEqual(process.returncode, 1)
        self.assertEqual(report["gate"], "fail")
        self.assertFalse(self.output.exists())

    def test_publish_failure_cleans_staging(self):
        with patch("codec_transit.cli.os.link", side_effect=OSError("not supported")):
            with self.assertRaises(OSError):
                publish(b"valid", self.output)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_publish_race_does_not_clobber(self):
        self.output.write_bytes(b"winner")
        with self.assertRaises(FileExistsError):
            publish(b"loser", self.output)
        self.assertEqual(self.output.read_bytes(), b"winner")
        self.assertFalse(list(self.root.glob(".codec-transit-*")))

    def test_codec_list_and_bad_limit(self):
        process = subprocess.run(
            [sys.executable, "-m", "codec_transit", "--list-codecs"], capture_output=True, text=True
        )
        self.assertEqual(process.returncode, 0)
        self.assertIn("cp932", json.loads(process.stdout)["codecs"])
        for value in ("0", str(10**100)):
            process = subprocess.run(
                [sys.executable, "-m", "codec_transit", "--max-bytes", value],
                capture_output=True,
                text=True,
            )
            self.assertEqual(process.returncode, 2)
            self.assertNotIn("Traceback", process.stderr)
