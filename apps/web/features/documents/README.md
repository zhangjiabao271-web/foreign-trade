# Document transfer

The ADR-020 review UI is under acceptance. Shared per-version review appears in shipment,
contract and export evidence areas, including finalized business records. Only document.read +
profit.read can inspect or decide; a specific version is downloaded for human review, then an
explicit release/restrict choice, explanation and confirmation are sent through the generated
command contract. Unchanged retries preserve the key and original digest/version. Session keys
remount editors; changed backend review snapshots reset stale forms. Restricted metadata has
explicit placeholder labels and unauthorized download controls are disabled/hidden.

Non-reviewers receive a current-version visibility description from the server's content_visible
projection; an accessible current version is not labelled unreviewed merely because the reader
lacks review authority. Older version visibility never determines the current-version message.
This description neither grants review controls nor changes download authorization.

Shared generated-client upload operation: checksum, scoped upload session, binary PUT,
then completion command. Callers capture their session client and handle query invalidation.
AVAILABLE state is determined by the backend scan job, not by successful PUT alone.

Shipment, contract and export hooks retain a session-scoped retry holder for an open form.
Metadata/checksum/target/replacement fingerprints reuse one key through session-create, PUT or
complete failures; changed payloads rotate identity. Success clears the attempt. A recovered
accepted version has no upload URL, so no second PUT/complete is issued. Upload clients capture
their starting credentials. Session changes obtain a separate holder; old in-flight work cannot
clear the new holder. No automatic background retry is introduced.

This holder is memory-only. After refresh/navigation, `resume-upload.tsx` instead selects the
current PENDING_UPLOAD version from the authorized DB-backed list and requires reselecting the
original file. Shared RHF/Zod controls validate a nonempty file up to 25 MiB, expose inline
errors and disable duplicate submissions. The backend compares name/MIME/size/SHA-256 before
re-signing the existing object key. Accepted recovery skips PUT/complete. No browser credentials,
PUT URLs or retry records are persisted by this flow. Session changes remount the file control.
Owner permissions/finality gate visibility; backend permissions and state remain authoritative.

`version-history.tsx` is shared by shipment and export evidence views. Native disclosure keeps
old evidence separate from current checklist facts. Only AVAILABLE versions expose a download
button; authorization is requested for the exact selected version, never a cached storage URL.
