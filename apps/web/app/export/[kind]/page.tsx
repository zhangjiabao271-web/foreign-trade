import { notFound } from "next/navigation";
import { ExportWorkspace } from "@/features/export/export-workspace";
export default async function ExportPage({
  params,
}: {
  params: Promise<{ kind: string }>;
}) {
  const { kind } = await params;
  if (kind !== "customs" && kind !== "refunds") notFound();
  return <ExportWorkspace kind={kind} />;
}
