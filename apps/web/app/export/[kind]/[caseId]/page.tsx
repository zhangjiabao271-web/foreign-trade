import { notFound } from "next/navigation";
import { ExportWorkspace } from "@/features/export/export-workspace";
export default async function ExportDetailPage({
  params,
}: {
  params: Promise<{ kind: string; caseId: string }>;
}) {
  const { kind, caseId } = await params;
  if (kind !== "customs" && kind !== "refunds") notFound();
  return <ExportWorkspace kind={kind} id={caseId} />;
}
