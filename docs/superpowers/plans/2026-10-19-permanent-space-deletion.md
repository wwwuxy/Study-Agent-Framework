# Permanent space deletion

User chose permanent removal of learning records and associated textbooks.

- Purge learning content, event evidence, local PDFs, sections and vectors; cancel indexing and erase checkpoints.
- Keep scrubbed space/asset/job tombstones for idempotency, late upload handles and retryable remote cleanup. No restore.
- Null the deleted space's provider association. Preserve other spaces and credentials; protect providers needed for cleanup.
- Narrow the event guard exception to an explicitly deleted space. Preserve ordinary append-only protection and tenant isolation.
- Add permanent confirmation, cleanup progress and retry in the manager. Migration never deletes existing spaces automatically.
- Verify lifecycle, late upload, cleanup retry, migrations, full checks, desktop/mobile UI and independent review.

## Verification

Implemented all items. Full `./scripts/check.sh`: 127 backend tests passed, one PostgreSQL-only race test skipped in the local SQLite environment; five frontend tests passed; production build and formatting checks passed. Seven desktop/mobile browser checks passed using isolated mocked accounts. Lifecycle tests cover actual answer/event removal, orphaned staging-file removal, other-space isolation, late uploads, credential protection, checkpoint/audit races, cleanup retry and uploader-crash lease recovery. Independent review findings were addressed and re-reviewed. Existing user data was not deleted during verification.
