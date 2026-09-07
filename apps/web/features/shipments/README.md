# Shipment workspace

The workspace reads shipment and document facts through the generated API client. Backend
Fulfillment owns capacity, state transitions, permissions and transactional evidence; browser
controls are not authorization or a replacement state machine.

Document polling refreshes the selected shipment query whenever document facts change,
including asynchronous AVAILABLE/REJECTED results after the upload command has returned.
The checklist is still read from the backend, never inferred from file type or PUT success.
It does not invalidate the document query itself, avoiding a self-triggered polling loop.

Write controls require current member-context permissions: `shipment.write` for creation,
`shipment.transition` for booking/milestones and `document.write` for upload/replacement.
Unknown/failed member context exposes no write controls. Delivered shipments retain read-only
documents. Upload controls cannot change the selected file/type during an active transfer.

Booking uses React Hook Form/Zod, a trimmed nonempty reference of at most 120 characters,
field-linked errors, first-invalid focus and pending protection. Failed values stay editable;
the backend command remains the state authority. ADR-025 freezes the form's opening shipment
version and sends it with a durable unchanged-body key. Other milestones send displayed counters.
Explicit original-variable retry survives refetch and later status changes; a stale planning form
can explicitly reset to the current version. Session/shipment remount discards retry identity,
not ordinary status refresh. Known finalized source orders hide fresh actions but retain authorized
receipt recovery. Backend validates even when source orders are outside the bounded browser list.
No browser-persisted keys, extra privileges or direct status writes are introduced.

Creation retains a synchronous ref-held key for an unchanged payload and sends it as
`Idempotency-Key`. Failure retains the form; changed contents rotate the key. Pending controls
are disabled. Closing/reopening does not retain the key: inspect the shipment list before
editing or discarding a form after a lost response. Backend capacity/state checks remain final.

Creation uses RHF/Zod for optional UUID/calendar fields and selected-line quantities. Quantities
remain exact strings (up to 14 integer and 4 decimal digits, positive); unselected lines do not
participate in quantity validation or the API payload. Selection supports 1–200 lines. Field
alerts and first-invalid focus complement backend validation, not replace capacity checks.
The form library owns field state; retry identity is kept separately in a synchronous ref.

Upload/replacement and isolated-test connection now also use RHF/Zod. Missing, empty or over
25 MiB files fail before upload-session allocation; accepted file/type choices still go through
the shared checksum/PUT/complete operation and backend scanning. Failure keeps selected input;
success clears file input and replacement mode. Cancellation restores the default document type.
Test connection validates organization UUID and nonblank credential before storing either value;
this is not real Logto acceptance or authorization based on local storage.

The creation source-order list supports explicit50-record cursor loading, retaining selected
quantities when older sources load. Details now directly request the selected shipment's bounded
source-lines endpoint, without scanning order pages. Protected source prose, loading and errors
have distinct labels and an explicit keyboard-accessible retry. Source caches use the sales-orders
invalidation prefix and existing session boundary so order/review changes refresh this projection.
Known finalized parent status still suppresses fresh commands; server checks remain authoritative.
The shipment list explicitly loads50-record cursor pages,
deduplicates IDs and retains loaded rows on failure with shared retry/restart controls.
The shared transfer now retains a keyed attempt
while the form remains open; session/PUT/complete failures can recover the original version.
Refreshing or leaving loses the open-form key. Current pending document cards now offer the
shared original-file reselect/resume operation based on DB metadata. It reuses the existing
version and refreshes shipment/file facts. Delivered shipments remain read-only. This does not
close the separate shipment-creation key persistence gap.
