# Documents

ADR-033 delegates scan-job creation and success recording to Platform-owned domain_jobs ports.
Documents retains upload/version/target validation, version-first locking and AVAILABLE replay.
Job lookup checks tenant and DOCUMENT_SCAN type before replay; owner success staging preserves
flush ordering and original progress/reference. Original domain evidence and null-actor worker
activity remain in the same transaction. No new scan engine or external side effect is implied.

ADR-020 document review is implemented; wider free-text policy remains open. Migration 0024 adds nullable,
organization-bound reviewer/time/content-digest facts, leaving all old versions confidential.
Review/restrict commands require document.read plus profit.read, an exact content digest,
opening version, explicit confirmation/reason and a durable command key. Decisions atomically
write activity/audit/outbox; replay reports current restriction and cannot undo later revocation.
The digest binds title/type/name/MIME/checksum/size/object key and pinned storage version.
New versions do not inherit release. Review does not change binary evidence or business finality.

Queries and upload/complete/resume command results return detached protected projections.
Unreleased title/file name/MIME are null for low roles; scan failure free text stays restricted.
Download signing requires cost authority or release of the exact verified version. Domain target
authorization is shared across review and document access. Previously signed download URLs may
remain valid for their original five-minute lifetime; stored copies cannot be remotely recalled.
Human content review is separate from the scan placeholder and does not certify malware safety.

Download signing runs without a database session held open. Before returning a newly signed
URL, the service rechecks target authorization, exact selected version, current release and
content fingerprint. A revoke during signing rejects the response; changed privileged evidence
returns a conflict. This does not revoke capabilities already returned before restriction.

PostgreSQL owns document identity, tenant ownership, immutable version metadata, checksums,
availability and business links. MinIO/S3 stores only binary objects under randomized,
organization-prefixed keys; object keys contain no customer names or other business PII.

The upload flow creates a `PENDING_UPLOAD` version and a 15-minute presigned PUT URL. Completion
checks object size, MIME type and SHA-256 before recording `UPLOADED` and queuing a PostgreSQL-backed
scan job. The current V1 worker is a deliberately minimal scan/parse framework: it idempotently marks
the version `AVAILABLE`; a production malware engine must replace that placeholder before accepting
untrusted external files. Downloads require organization authorization and use a five-minute
presigned URL. Permanent public URLs are never stored.

Download signatures include an attachment Content-Disposition with the authorized selected
version's UTF-8 filename (RFC 5987 encoding and a safe ASCII fallback). Header delimiters and
control characters are percent-encoded, not interpolated as raw header values. The exact pinned
storage version and five-minute lifetime are unchanged. This instructs browser saving but does
not prove a local file was saved; real-browser byte/download acceptance remains separate.

The MinIO Python SDK is Apache-2.0 licensed.

The internal storage client and browser signing endpoint are configured separately.
`MINIO_PUBLIC_ENDPOINT` is a browser-reachable host:port (no URL path); adjust it when using
a non-default published port or a remote browser. Public TLS uses `MINIO_PUBLIC_SECURE`.
Signing uses an explicit region and performs no region-discovery HTTP call. Upload target
authorization occurs before storage calls and is rechecked in the short business transaction.

ADR-010 requires bucket versioning. Completion pins the exact storage version inspected and
downloads sign that immutable version. Reusing a PUT URL cannot change accepted evidence.
Legacy versions remain inaccessible until their original checksum is revalidated by completion.
Production credentials must not be allowed to delete object versions.

`POST /{document_id}/version-upload-sessions` accepts `expected_version` and new file metadata.
It creates a new key and increments the current version; old versions remain intact. The new
current version does not satisfy any checklist until completion and scanning succeed.
Finalized business targets reject new uploads, replacements, and pending-upload completion.
Legacy checksum revalidation and downloads remain allowed for finalized evidence.
The literal S3 `null` version is mutable and is never accepted as an immutable pointer.
Legacy unversioned binaries require a separately audited storage-version migration before
checksum revalidation; simply enabling bucket versioning does not version older objects.

`POST /{document_id}/versions/{version_id}/download-session` downloads an explicit historical
version. Both document and version must belong to the current organization and to each other;
only AVAILABLE, storage-pinned versions can be signed. Historical downloads remain valid after
business finalization and never change which current version satisfies a checklist.

SALES_CONTRACT is an explicit document type. The `evidence.py` application port verifies the
specific version's organization, order link, type, availability, checksum, size and immutable
storage pointer before a contract command pins it. This is metadata verification, not legal
signature validation. The sales contract command does not change document-owned metadata.

Both upload-session creation endpoints accept an optional Idempotency-Key. Validated metadata,
target and replacement opening version are hashed together under the organization-scoped key.
Document/version/link, evidence and completed key commit atomically. Matching retries return
the original version, not a new document or replacement; changed payloads conflict. Header
omission preserves legacy allocation behavior and does not provide uncertain-result recovery.

Pending replay reauthorizes the target, requires a nonfinalized target and current version,
and signs the original object key outside the DB transaction, then rechecks facts after signing.
Accepted replay returns upload_url=null and the original version without signing another PUT;
finalized targets allow this read-only recovery. Rejected/superseded pending versions refuse
resumption. Existing pinned completion and scanning rules are unchanged. No schema migration
or storage SDK dependency change is needed; regenerated clients model the nullable URL.

`POST /{document_id}/versions/{version_id}/upload-session` recovers a persisted version after
reload without the original creation key. Reselected file name, MIME, size and SHA-256 must
match the immutable expected metadata. Document/version relationship, organization, write and
target-read permissions are checked before signing and again after signing. This operation
creates no document, version, business evidence or key; completion retains its atomic evidence.
Accepted versions return no PUT URL, even after target finalization. No migration is needed.
