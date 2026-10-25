"""Explicit codec evaluation; strict encoding success is not a preservation proof."""

import codecs
import hashlib
import platform

# Fixed text-only codec set. Native-endian UTF-16/32 and stateful codecs are excluded.
CODECS = (
    "ascii",
    "utf-8",
    "utf-8-sig",
    "utf-16-le",
    "utf-16-be",
    "utf-32-le",
    "utf-32-be",
    "iso8859-1",
    "iso8859-15",
    "cp1250",
    "cp1251",
    "cp1252",
    "cp1253",
    "cp1254",
    "cp1255",
    "cp1256",
    "cp1257",
    "cp1258",
    "cp437",
    "cp850",
    "cp932",
    "shift_jis",
    "euc_jp",
    "gbk",
    "gb18030",
    "big5",
    "cp950",
    "cp949",
    "euc_kr",
)
CANONICAL = frozenset(codecs.lookup(name).name for name in CODECS)


class TransitError(ValueError):
    def __init__(self, code, start=None, end=None):
        self.code, self.start, self.end = code, start, end
        super().__init__(code)


def canonical(name):
    try:
        result = codecs.lookup(name).name
    except LookupError as exc:
        raise TransitError("unsupported_codec") from exc
    if result not in CANONICAL:
        raise TransitError("unsupported_codec")
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def difference(left, right):
    """One enclosing difference interval after removing equal prefix and suffix."""
    prefix = 0
    limit = min(len(left), len(right))
    while prefix < limit and left[prefix] == right[prefix]:
        prefix += 1
    if prefix == len(left) == len(right):
        return None
    suffix = 0
    while suffix < limit - prefix and left[-suffix - 1] == right[-suffix - 1]:
        suffix += 1
    return {
        "input_start": prefix,
        "input_end": len(left) - suffix,
        "returned_start": prefix,
        "returned_end": len(right) - suffix,
    }


def unencodable_ranges(text, codec, max_findings):
    cache = {}
    ranges = []
    total_ranges = bad_count = 0
    start = None
    for index, char in enumerate(text):
        if char not in cache:
            try:
                char.encode(codec, "strict")
                cache[char] = True
            except UnicodeEncodeError:
                cache[char] = False
        if not cache[char]:
            bad_count += 1
            if start is None:
                start = index
        elif start is not None:
            total_ranges += 1
            if len(ranges) < max_findings:
                ranges.append({"start": start, "end": index})
            start = None
    if start is not None:
        total_ranges += 1
        if len(ranges) < max_findings:
            ranges.append({"start": start, "end": len(text)})
    return {
        "unencodable_codepoints": bad_count,
        "range_count": total_ranges,
        "ranges": ranges,
        "ranges_omitted": total_ranges - len(ranges),
    }


def inspect_bytes(
    data: bytes,
    source: str,
    targets,
    *,
    require_byte_roundtrip=False,
    max_findings=50,
    want_output=False,
):
    """Return a JSON-compatible report and an optional verified destination payload."""
    if type(max_findings) is not int or not 0 < max_findings <= 2_147_483_647:
        raise TransitError("invalid_finding_limit")
    source = canonical(source)
    targets = [canonical(x) for x in targets]
    if not 1 <= len(targets) <= 8 or len(set(targets)) != len(targets):
        raise TransitError("target_count_or_alias_duplicate")
    if want_output and len(targets) != 1:
        raise TransitError("output_requires_one_target")
    try:
        text = data.decode(source, "strict")
    except UnicodeDecodeError as exc:
        raise TransitError("source_decode_error", exc.start, exc.end) from exc
    source_check = {"exact": False}
    try:
        reconstructed = text.encode(source, "strict")
        source_check = {
            "exact": reconstructed == data,
            "returned_bytes": len(reconstructed),
            "difference_bytes": difference(data, reconstructed),
        }
    except UnicodeEncodeError as exc:
        source_check["error"] = {
            "code": "source_reencode_error",
            "start": exc.start,
            "end": exc.end,
        }
    report = {
        "schema_version": 1,
        "tool": "codec-transit",
        "python_version": platform.python_version(),
        "status": "complete",
        "source": {
            "codec": source,
            "bytes": len(data),
            "codepoints": len(text),
            "sha256": digest(data),
        },
        "source_byte_roundtrip": source_check,
        "require_byte_roundtrip": require_byte_roundtrip,
        "targets": [],
        "output_written": False,
    }
    payload = None
    for target in targets:
        item = {"codec": target, "encodable": False, "unicode_roundtrip": None}
        try:
            encoded = text.encode(target, "strict")
        except UnicodeEncodeError as exc:
            item["issue"] = "unencodable"
            item["first_error"] = {"start": exc.start, "end": exc.end}
            item.update(unencodable_ranges(text, target, max_findings))
            report["targets"].append(item)
            continue
        item.update(encodable=True, bytes=len(encoded), sha256=digest(encoded))
        try:
            returned = encoded.decode(target, "strict")
        except UnicodeDecodeError as exc:
            item["issue"] = "target_decode_error"
            item["error_bytes"] = {"start": exc.start, "end": exc.end}
            item["unicode_roundtrip"] = False
            report["targets"].append(item)
            continue
        exact = returned == text
        item["unicode_roundtrip"] = exact
        item["returned_codepoints"] = len(returned)
        item["difference_codepoints"] = difference(text, returned)
        if not exact:
            item["issue"] = "unicode_changed"
        if exact and want_output:
            payload = encoded
        report["targets"].append(item)
    passed = all(item["unicode_roundtrip"] is True for item in report["targets"])
    if require_byte_roundtrip and not source_check["exact"]:
        passed = False
    report["gate"] = "pass" if passed else "fail"
    return report, payload if passed else None
