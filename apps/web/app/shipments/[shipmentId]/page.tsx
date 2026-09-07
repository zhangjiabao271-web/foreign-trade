import { ShipmentWorkspace } from "@/features/shipments/shipment-workspace";

export default async function ShipmentDetailPage({
  params,
}: {
  params: Promise<{ shipmentId: string }>;
}) {
  return <ShipmentWorkspace initialShipmentId={(await params).shipmentId} />;
}
