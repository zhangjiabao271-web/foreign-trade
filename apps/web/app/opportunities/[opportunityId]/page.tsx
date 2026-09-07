import { OpportunityWorkspace } from "../../../features/opportunities/opportunity-workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ opportunityId: string }>;
}) {
  const { opportunityId } = await params;
  return <OpportunityWorkspace id={opportunityId} />;
}
