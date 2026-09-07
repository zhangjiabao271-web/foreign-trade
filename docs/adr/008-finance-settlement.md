# ADR-008: V1 settlement and completion rules

Status: Accepted for implementation under the approved V1 construction scope.

The implementation guide delegates installment dates, completion documents and waiver
permissions to the corresponding slice. V1 uses deposit plus balance in the order currency,
ROUND_HALF_UP to four places, positive allocations and separate reversal facts. Idempotency
keys identify commands, so one payment may fund multiple receivables or the same receivable
in several commands. Database locking serializes payment availability and receivable balance.

The lock order is payment -> sales orders sorted by UUID -> receivables sorted by UUID.
Completion uses order -> receivables; due-date refresh only locks receivables. Document number
allocation is an atomic organization/type/year upsert, including first-number creation.

Completion requires full delivery and available commercial invoice/packing list for every
shipment, full receivable coverage, payment settlement and no open order tasks. ADMIN/MANAGER
may waive financial settlement with a reason; debt is still visible and no allocation is invented.
Reversing payment against a completed order, or deposit after shipment planning, requires a
future compensating workflow and returns an explicit conflict in V1. Core facts are never erased.

Production provider choices remain adapters/configuration. This decision neither introduces
automatic funds movement nor a financial general ledger.
