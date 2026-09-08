# Action overview

Organization-scoped PostgreSQL action queues, independently paginated and refreshed.
Counts describe the visible page, not totals. Server permissions govern visibility.
Session changes partition caches without putting credentials in query keys.
Manual refresh invalidates only that queue's first page and resets to offset zero; it reloads from
the server. Refresh on the first page refetches it directly. Automatic polling preserves the
current page. Pending requests disable refresh, and other queues keep their own positions.
