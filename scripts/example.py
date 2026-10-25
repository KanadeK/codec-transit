"""Demonstrate successful migration and an encodable-but-lossy rejection."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    source, destination = root / "legacy.txt", root / "utf8.txt"
    source.write_bytes("€ café\r\n".encode("cp1252"))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codec_transit",
            str(source),
            "--from",
            "cp1252",
            "--to",
            "utf8",
            "--output",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["output_written"]
    assert destination.read_bytes() == "€ café\r\n".encode()
    source.write_bytes("〜".encode())
    rejected = subprocess.run(
        [
            sys.executable,
            "-m",
            "codec_transit",
            str(source),
            "--from",
            "utf8",
            "--to",
            "cp932",
            "--output",
            str(root / "bad.txt"),
        ],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["targets"][0]["issue"] == "unicode_changed"
    assert not (root / "bad.txt").exists()
    print("PASS: CP1252 migration preserved text; CP932 wave-dash substitution was rejected.")
