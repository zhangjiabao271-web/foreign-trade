import { QuotationWorkspace } from "@/features/quotations/quotation-workspace";

export default async function QuotationDetailPage({
  params,
}: {
  params: Promise<{ quotationId: string }>;
}) {
  return <QuotationWorkspace initialQuotationId={(await params).quotationId} />;
}
