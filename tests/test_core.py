import hashlib
import random
import unittest

from codec_transit.core import CODECS, TransitError, canonical, difference, inspect_bytes


class CoreTests(unittest.TestCase):
    def test_cp932_encodable_does_not_mean_unicode_preserved(self):
        raw = "before〜after".encode()
        report, payload = inspect_bytes(raw, "utf8", ["cp932"], want_output=True)
        target = report["targets"][0]
        self.assertTrue(target["encodable"])
        self.assertFalse(target["unicode_roundtrip"])
        self.assertEqual(target["issue"], "unicode_changed")
        self.assertEqual(
            target["difference_codepoints"],
            {"input_start": 6, "input_end": 7, "returned_start": 6, "returned_end": 7},
        )
        self.assertEqual(report["gate"], "fail")
        self.assertIsNone(payload)

    def test_cp932_source_byte_canonicalization_is_separate(self):
        raw = bytes.fromhex("fbfc")
        report, payload = inspect_bytes(raw, "cp932", ["utf8"], want_output=True)
        self.assertFalse(report["source_byte_roundtrip"]["exact"])
        self.assertTrue(report["targets"][0]["unicode_roundtrip"])
        self.assertEqual(report["gate"], "pass")
        self.assertEqual(payload.decode("utf8"), "髙")
        strict, payload = inspect_bytes(
            raw, "cp932", ["utf8"], want_output=True, require_byte_roundtrip=True
        )
        self.assertEqual(strict["gate"], "fail")
        self.assertIsNone(payload)

    def test_unencodable_ranges_are_complete(self):
        text = "a中😀béc中d"
        report, _ = inspect_bytes(text.encode(), "utf8", ["ascii"], max_findings=2)
        target = report["targets"][0]
        self.assertFalse(target["encodable"])
        self.assertEqual(target["unencodable_codepoints"], 4)
        self.assertEqual(target["range_count"], 3)
        self.assertEqual(target["ranges"], [{"start": 1, "end": 3}, {"start": 4, "end": 5}])
        self.assertEqual(target["ranges_omitted"], 1)

    def test_final_unencodable_run(self):
        report, _ = inspect_bytes("x中😀".encode(), "utf8", ["ascii"])
        self.assertEqual(report["targets"][0]["ranges"], [{"start": 1, "end": 3}])

    def test_multiple_targets_all_must_pass_gate(self):
        report, _ = inspect_bytes("€".encode(), "utf8", ["cp1252", "ascii", "utf-16-le"])
        self.assertEqual([x["unicode_roundtrip"] for x in report["targets"]], [True, None, True])
        self.assertEqual(report["gate"], "fail")

    def test_empty_and_bom(self):
        report, payload = inspect_bytes(b"", "utf8", ["utf-8-sig"], want_output=True)
        self.assertEqual(payload, b"\xef\xbb\xbf")
        self.assertEqual(report["gate"], "pass")
        report, payload = inspect_bytes(b"\xef\xbb\xbfA", "utf-8-sig", ["utf8"], want_output=True)
        self.assertEqual(payload, b"A")
        self.assertTrue(report["source_byte_roundtrip"]["exact"])

    def test_utf8_sig_missing_bom_reported(self):
        report, _ = inspect_bytes(b"A", "utf-8-sig", ["utf8"])
        self.assertFalse(report["source_byte_roundtrip"]["exact"])
        self.assertEqual(report["gate"], "pass")

    def test_line_endings_and_nuls_preserved(self):
        text = "é\r\n\x00last\r"
        report, payload = inspect_bytes(text.encode(), "utf8", ["utf-16-be"], want_output=True)
        self.assertEqual(payload.decode("utf-16-be"), text)
        self.assertEqual(report["targets"][0]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_decoding_failure_has_byte_offsets(self):
        with self.assertRaises(TransitError) as caught:
            inspect_bytes(b"abc\xff", "utf8", ["cp1252"])
        self.assertEqual(
            (caught.exception.code, caught.exception.start, caught.exception.end),
            ("source_decode_error", 3, 4),
        )

    def test_allowlist_and_aliases(self):
        self.assertEqual(canonical("latin1"), "iso8859-1")
        for name in ("base64_codec", "rot_13", "unicode_escape", "utf16", "iso2022_jp", "absent"):
            with self.subTest(codec=name), self.assertRaises(TransitError):
                canonical(name)

    def test_bad_target_lists(self):
        for targets in ([], ["latin1", "iso8859-1"], list(CODECS[:9])):
            with self.subTest(targets=targets), self.assertRaises(TransitError):
                inspect_bytes(b"a", "utf8", targets)
        with self.assertRaises(TransitError):
            inspect_bytes(b"a", "utf8", ["ascii", "utf8"], want_output=True)

    def test_randomized_unicode_payloads(self):
        rng = random.Random(205)
        for _ in range(100):
            text = "".join(
                chr(rng.choice([rng.randrange(0xD800), rng.randrange(0xE000, 0x110000)]))
                for _ in range(30)
            )
            for target in (
                "utf-8",
                "utf-8-sig",
                "utf-16-le",
                "utf-16-be",
                "utf-32-le",
                "utf-32-be",
            ):
                report, payload = inspect_bytes(text.encode(), "utf8", [target], want_output=True)
                self.assertEqual(report["gate"], "pass")
                self.assertEqual(payload, text.encode(target))
                self.assertEqual(payload.decode(target), text)

    def test_every_allowed_codec_ascii(self):
        for target in CODECS:
            with self.subTest(codec=target):
                report, payload = inspect_bytes(b"Hello\r\n42", "ascii", [target], want_output=True)
                self.assertEqual(report["gate"], "pass")
                self.assertEqual(payload.decode(target), "Hello\r\n42")

    def test_difference_envelope(self):
        self.assertIsNone(difference("abc", "abc"))
        self.assertEqual(
            difference("ac", "abbc"),
            {"input_start": 1, "input_end": 1, "returned_start": 1, "returned_end": 3},
        )
        self.assertEqual(
            difference(b"abc", b"ac"),
            {"input_start": 1, "input_end": 2, "returned_start": 1, "returned_end": 1},
        )

    def test_valid_roundtrip_does_not_determine_intended_encoding(self):
        report, _ = inspect_bytes("é".encode(), "latin1", ["utf8"])
        self.assertEqual(report["gate"], "pass")
        self.assertEqual(report["source"]["codepoints"], 2)
