"use client";

import type { useSalesOrders } from "./api";
import { CursorPageControls } from "../../components/cursor-page-controls";

export function OrderPageControls({
  query,
  disabled = false,
}: {
  query: ReturnType<typeof useSalesOrders>;
  disabled?: boolean;
}) {
  return <CursorPageControls query={query} label="订单" disabled={disabled} />;
}
