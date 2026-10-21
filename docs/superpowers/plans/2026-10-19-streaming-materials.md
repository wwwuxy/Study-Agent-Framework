# Streaming materials implementation plan

**Goal:** Upload, persist, forward and download PDF files with bounded application buffers, retaining the configured 1024 MiB ceiling.

**Design:** Apply streaming to every file size so there is one upload path. Receive into a private temporary file in the material directory; validate PDF metadata, header/tail, active-content signatures and SHA-256 incrementally. Atomically publish only validated files; remove temporary/published files on aborted persistence. Forward an open binary file through HTTPX multipart, which reads bounded chunks and rewinds seekable files for retries. CLI uploads/downloads use file streams. Existing HTTP APIs and provider selection remain compatible.

**Constraints:** No local document extraction, OCR or embedding; preserve explicit consent, idempotency, user/space isolation and remote cleanup. Do not alter unrelated pending UI work. No new runtime dependencies or schema migration. Provider limits and remote operation timeouts still apply.

**Verification focus:** signatures split across chunks; missing/false Content-Length; cancellation/disconnect and disk/database errors; upload retry from byte zero; no overwriting local downloads and removal of partial downloads.

- [x] Storage and upload: add chunked PDF validation, private staging with atomic publication, incremental hashing, size enforcement and cleanup. Test persistence visibility before completion, malicious boundaries, aborts and idempotent retries.
- [x] Worker forwarding: open original files rather than reading all bytes; keep handles open through remote upload and close on errors/cancellation. Verify HTTPX multipart streams/retries and worker closure without whole-file reads.
- [x] CLI: send binary streams with known size; stream responses to exclusively created private downloads and remove partial files. Update previous size tests to assert streamed uploads without allocating GiB payloads.
- [x] Documentation and verification: update size/memory explanation; run full checks and focused memory regression with generated input, then request independent review. Actual provider 1 GiB acceptance is outside local streaming validation.

**Verified:** `./scripts/check.sh`: 119 backend tests passed, 1 PostgreSQL-specific test skipped, 5 frontend tests passed, lint/format/shell checks and production build passed. Offline generated 1 GiB disk-to-multipart transfer: exact byte count and SHA-256 matched, peak RSS 43.42 MiB and Python peak allocation 1.48 MiB, temporary files cleaned. Independent review: no findings. No external provider calls or schema changes.
