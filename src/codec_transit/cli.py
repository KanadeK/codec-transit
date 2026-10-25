import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .core import CODECS, TransitError, inspect_bytes


def positive(value):
    value = int(value)
    if not 0 < value <= 2_147_483_647:
        raise argparse.ArgumentTypeError("must be between 1 and 2147483647")
    return value


def publish(payload, output):
    """Publish complete bytes without replacing any existing destination."""
    path = Path(output)
    fd, temporary = tempfile.mkstemp(prefix=".codec-transit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Transcode only when Unicode identity is preserved."
    )
    parser.add_argument("--version", action="version", version=f"codec-transit {__version__}")
    parser.add_argument("--list-codecs", action="store_true")
    parser.add_argument("input", nargs="?", help="regular file to read without newline translation")
    parser.add_argument("--from", dest="source", help="explicit source codec")
    parser.add_argument(
        "--to", dest="targets", action="append", help="repeat for up to eight targets"
    )
    parser.add_argument("--output", help="new file; requires exactly one target")
    parser.add_argument("--require-byte-roundtrip", action="store_true")
    parser.add_argument("--max-bytes", type=positive, default=16 * 1024 * 1024)
    parser.add_argument("--max-findings", type=positive, default=50)
    args = parser.parse_args(argv)
    if args.list_codecs:
        print(json.dumps({"codecs": CODECS}))
        return 0
    if args.input is None or args.source is None or args.targets is None:
        parser.error("input, --from and --to are required unless --list-codecs is used")
    try:
        path = Path(args.input)
        if not path.is_file():
            raise TransitError("input_not_regular_file")
        if args.output and os.path.lexists(args.output):
            raise TransitError("output_exists")
        with path.open("rb") as stream:
            data = stream.read(args.max_bytes + 1)
        if len(data) > args.max_bytes:
            raise TransitError("input_byte_limit")
        report, payload = inspect_bytes(
            data,
            args.source,
            args.targets,
            require_byte_roundtrip=args.require_byte_roundtrip,
            max_findings=args.max_findings,
            want_output=args.output is not None,
        )
        status = int(report["gate"] != "pass")
        if args.output and payload is not None:
            publish(payload, args.output)
            report["output_written"] = True
    except (TransitError, OSError) as exc:
        report = {
            "schema_version": 1,
            "tool": "codec-transit",
            "status": "error",
            "output_written": False,
            "error": {"code": exc.code if isinstance(exc, TransitError) else "io_error"},
        }
        if isinstance(exc, TransitError) and exc.start is not None:
            report["error"].update(start=exc.start, end=exc.end)
        status = 2
    try:
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + "\n")
    except BrokenPipeError:
        return 2
    return status
