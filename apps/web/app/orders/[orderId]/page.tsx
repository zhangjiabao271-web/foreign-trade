import { OrderWorkspace } from "@/features/orders/order-workspace";

export default async function OrderDetailPage({
  params,
}: {
  params: Promise<{ orderId: string }>;
}) {
  return <OrderWorkspace initialOrderId={(await params).orderId} />;
}
