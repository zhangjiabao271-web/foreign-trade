"use client";

import { useQuery } from "@tanstack/react-query";
import { parseApiError } from "@trade-workbench/api-client";
import { WorkTextReview } from "../finance/work-review";
import { useMemberContext } from "../overview/api";
import { sessionClient, useSessionScope } from "../overview/session";

export function InquirySource({ id }: { id: string }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const allowed = member.data?.permissions.includes("inquiry.read") ?? false;
  const query = useQuery({
    queryKey: ["inquiry-source", scope, id],
    enabled: allowed,
    retry: false,
    queryFn: async () => {
      const result = await sessionClient().GET(
        "/api/v1/inquiries/{inquiry_id}",
        {
          params: { path: { inquiry_id: id } },
        },
      );
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
  if (!allowed) return null;
  return (
    <section aria-label="询盘说明审核">
      <h3>来源询盘</h3>
      {query.isPending && <p role="status">正在读取询盘…</p>}
      {query.isError && <p role="alert">无法读取询盘，请重试。</p>}
      <button
        className="quiet-button"
        disabled={query.isFetching}
        onClick={() => query.refetch()}
      >
        刷新询盘
      </button>
      {query.data && (
        <>
          <p>客户询盘编号：{query.data.customer_reference ?? "未填写"}</p>
          <p>
            {query.data.content_visible
              ? query.data.description
              : "询盘说明待审核，当前不可见"}
          </p>
          <WorkTextReview
            sourceKind="inquiry"
            recordId={id}
            onChanged={() => query.refetch()}
          />
        </>
      )}
    </section>
  );
}
