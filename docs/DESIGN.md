# Design and acceptance

Target users: maintainers moving bounded text exchange files into or out of legacy
code pages. The MVP compares explicit destination choices, distinguishes Unicode
identity from canonical source-byte spelling, and emits a verified new file.

All input is decoded strictly using a fixed allowlist of standard text codecs.
The selected runtime's full-string encode and decode is the preservation oracle.
The tool compares exact strings rather than assuming a successful encode is enough.
Unencodable scalar ranges are counted in a linear scan with cached character
encodability. Mismatch diagnostics trim common prefix and suffix in linear time;
there is no potentially quadratic fuzzy alignment. The default 16 MiB limit bounds
whole-file memory. Only a single requested destination can be published.

Acceptance includes CP932 wave-dash substitution, CP932 duplicate byte mappings,
ASCII failures, UTF-8 BOM semantics, explicit-endian supplementary characters,
embedded NULs, CRLF preservation, all supported codecs on ASCII, randomized Unicode
through six Unicode codecs, no-clobber publication and cleanup after link failure.

Review: source bytes are never written; no codecs or inputs are executed as code;
binary transformations are refused; target aliases are deduplicated; output is
published only after verification. Runtime code has no third-party dependencies,
network calls, subprocesses or credential access. Hash equality disclosure, memory
limits, CPython-specific behavior and source-codec uncertainty are documented.
