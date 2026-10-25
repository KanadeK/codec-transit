# codec-transit

Preflight an explicit text encoding migration, then write a new file **only when
decoding the destination reproduces every source Unicode code point**.

Strict encoding can succeed and still change text: Python's CP932 encoder accepts
U+301C WAVE DASH `〜`, but decoding those bytes returns U+FF5E FULLWIDTH TILDE `～`.
codec-transit catches this distinction, compares up to eight destination codecs,
and separately checks whether source bytes re-encode identically.

Python 3.11+, no runtime dependencies, offline. No encoding guessing, replacement
characters, normalization or automatic repairs.

## Install and try

```sh
git clone https://github.com/KanadeK/codec-transit.git
cd codec-transit
python -m venv .venv
# bash/zsh: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
python scripts/example.py
codec-transit examples/wave-dash.txt --from utf8 --to utf8 --to cp932
```

The last command intentionally exits **1**: UTF-8 preserves the text; CP932 does
not. The example script verifies a successful CP1252→UTF-8 migration and rejection
of a CP932 Unicode substitution, then removes all temporary files.

To migrate your own known-CP1252 file:

```sh
codec-transit legacy.txt --from cp1252 --to utf8 --output migrated.txt
```

`python -m codec_transit` is equivalent. Omit `--output` for read-only comparison.
Output requires one destination codec and a new path; no existing file is overwritten.

## Two independent preservation questions

1. **Destination Unicode identity**: decode the source with the declared codec,
   encode strictly to the target, decode strictly from it, compare the exact strings.
   A failed encode, failed decode or changed code point fails the gate.
2. **Source byte round-trip**: decode then re-encode with the source codec and compare
   original bytes. Alternate legacy byte mappings or a missing UTF-8 BOM can change
   bytes even when the decoded text is preserved. This is reported separately.

Default output gating requires destination Unicode identity. Add
`--require-byte-roundtrip` if source-byte reconstruction must also be exact. For
example, CP932 bytes `FB FC` decode to U+9AD9 but Python re-encodes that character as
`EE E0`; UTF-8 migration can preserve the text even though the original byte spelling
is not reproducible through that codec. The input file itself is always retained.

Passing a round-trip test does **not** prove the source codec was intended: UTF-8
bytes decoded as Latin-1 can round-trip perfectly while representing the wrong text.
Choose codecs from trusted format metadata. Reports describe the current CPython
codec implementation, not browser WHATWG, ICU, .NET or every tool using similar names.

## Reports and exit status

The JSON report includes canonical codec names, Python version, input/output byte
counts and SHA-256 digests, source-byte round-trip status, and each destination's
encodability and Unicode round-trip result. Digests can reveal file equality and
are not anonymization. No source text, offending byte values or filesystem paths
are printed by runtime diagnostics.

Unencodable characters are grouped into adjacent ranges with complete code-point
and range counts; `--max-findings` caps stored examples (default 50). Positions are
zero-based, half-open offsets into the **decoded source text**. Source decode errors
and source byte-difference intervals use byte offsets instead.

`difference_codepoints` and `difference_bytes` describe one enclosing difference
after equal prefix/suffix removal. They are not minimal edit scripts and can contain
unchanged interior material. JSON names say `input_*` and `returned_*` to distinguish
the two coordinate spaces.

| Exit | Meaning |
|---|---|
| 0 | Every requested target passes; output written if requested |
| 1 | Complete comparison with at least one failed preservation requirement |
| 2 | Invalid input, source decode error, unsupported codec, limit or I/O error |

Inspect individual target results when a multi-target comparison exits 1. A valid
target can still be chosen in a subsequent single-target conversion.

## Supported codecs and limits

`codec-transit --list-codecs` lists the fixed text-codec allowlist. It includes
UTF-8, UTF-8-SIG, explicit-endian UTF-16/32, ASCII, Latin-1/15, Windows CP1250–1258,
CP437/850, CP932, Shift_JIS, EUC-JP, GBK/GB18030, Big5/CP950, CP949 and EUC-KR.
Python aliases are accepted, but duplicate aliases in one target list are rejected.
Binary transforms, Unicode escape codecs, stateful ISO-2022 codecs and native-endian
`utf-16`/`utf-32` are deliberately unsupported.

`utf-8-sig` consumes an optional initial BOM and writes one on encode. Explicit-endian
UTF-16/32 preserve a decoded U+FEFF as content; they do not automatically remove a BOM.
Use format-aware preprocessing if that is needed. Files are opened as bytes, so line
endings and embedded NULs undergo no implicit text-mode translation.

Default input limit is **16 MiB** (`--max-bytes`). The whole source and one destination
are processed in memory; this release is for bounded exchange files, not multi-GB
archives. No batch directory traversal. The temporary destination is published by
an atomic no-clobber hard link on the same filesystem. NTFS, APFS and typical Linux
filesystems support this; unsupported filesystems fail without publishing output.
A process kill can leave a `.codec-transit-*` staging file. Keep source paths stable
during a run and use directories you control.

## Alternatives, development and cleanup

[iconv-lite issue 145](https://github.com/pillarjs/iconv-lite/issues/145) and
[CPython issue 7983](https://bugs.python.org/issue7983) document relevant mapping
differences. iconv performs general conversions; [ftfy](https://github.com/rspeer/python-ftfy)
repairs damaged Unicode text. [encoding-roundtrip-audit](https://github.com/mytestapp20261001-collab/encoding-roundtrip-audit)
checks source-byte round-trips read-only. codec-transit concentrates on comparing
destination preservation and producing an independently decoded, verified file.
It does not ship any third-party codec implementation or copied code.

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests, lint and clean-wheel verification.
Uninstall with `python -m pip uninstall codec-transit`; remove the virtual environment
and any generated files you no longer need. MIT license.

## 中文说明

本工具先按明确指定的编码解码，再检查目标编码往返后是否保留每一个 Unicode 码点，
通过后才写入新文件。它可以发现“编码成功，但波浪号等字符悄悄改变”的情况，并把源文件
字节往返与目标文本保真分开报告。不会猜测编码、替换坏字符或覆盖原文件。默认处理不超过
16 MiB 的文件；不同运行时的代码页实现可能不同，验证结论仅适用于当前 Python 编解码器。
