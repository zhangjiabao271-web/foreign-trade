# ADR-010: Pin immutable object-storage versions

Status: Accepted within the approved file-integrity acceptance scope.

Presigned PUT URLs can be reused while valid. Random keys alone do not prevent overwrites.
Enable S3/MinIO bucket versioning and pin the exact storage version ID verified by completion
in PostgreSQL. Inspection hashes that precise version and downloads sign that version, never
the mutable latest object. Reusing an upload URL creates another storage version but cannot
change the binary referenced by an accepted document version. Production bucket policy must
also deny version deletion to ordinary application identities.

The additive nullable column preserves old metadata. Legacy unpinned versions cannot be
downloaded until completion revalidates the existing expected checksum and pins the object.
No migration deletes objects or rewrites historical checksum facts. New replacements use new
document-version IDs/keys and optimistic document versions, not overwrites of old versions.

Storage calls stay outside business transactions. PostgreSQL remains the source of ownership,
checksum, availability and the exact evidence pointer. A full backup must retain object versions.
