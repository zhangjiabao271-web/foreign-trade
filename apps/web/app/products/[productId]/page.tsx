import { CatalogWorkspace } from "../../../features/catalog/catalog-workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ productId: string }>;
}) {
  const { productId } = await params;
  return <CatalogWorkspace id={productId} />;
}
