import { CompanyWorkspace } from "../../../features/companies/company-workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ companyId: string }>;
}) {
  const { companyId } = await params;
  return <CompanyWorkspace id={companyId} />;
}
