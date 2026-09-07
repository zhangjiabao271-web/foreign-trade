import { LeadWorkspace } from "@/features/leads/lead-workspace";

export default async function LeadDetailPage({
  params,
}: {
  params: Promise<{ leadId: string }>;
}) {
  return <LeadWorkspace initialLeadId={(await params).leadId} />;
}
