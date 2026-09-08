"use client";

import { useQuery } from "@tanstack/react-query";
import { parseApiError } from "@trade-workbench/api-client";
import { Button } from "@trade-workbench/ui";
import { sessionClient } from "../overview/session";
import { expenseError } from "./expense-form";

function Estimate({ scope, orderId }: { scope: string; orderId: string }) {
  const query = useQuery({
    queryKey: ["funding-estimate", scope, orderId],
    retry: false,
    queryFn: async () => {
      const result = await sessionClient().GET(
        "/api/v1/sales-orders/{order_id}/funding-estimate",
        { params: { path: { order_id: orderId } } },
      );
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
  return (
    <section className="finance-payment" aria-label="垫资估算">
      <h3>垫资估算 · 非实际现金缺口</h3>
      <p>报价成本＋额外费用净额－本订单净核销收款，最低为零。</p>
      {query.isFetching && <p role="status">正在更新垫资估算…</p>}
      {query.isError && <p role="alert">{expenseError(query.error)}</p>}
      {query.data && !query.isError && (
        <>
          <strong>
            {query.data.estimated_funding_need} {query.data.currency_code}
          </strong>
          <p>
            报价成本：{query.data.quoted_total_cost} {query.data.currency_code}
          </p>
          <p>
            额外费用净额：{query.data.net_additional_cost}{" "}
            {query.data.currency_code}
          </p>
          <p>
            本订单净核销收款：{query.data.net_allocated_receipts}{" "}
            {query.data.currency_code}
          </p>
        </>
      )}
      <p>冲销已扣回，报价已含费用不重复计入，未核销收款不计入。</p>
      <p>
        未考虑供应商付款日程、账期和未登记费用；不代表资金峰值。估算为零也不保证无需准备资金。
      </p>
      <Button
        variant="quiet"
        disabled={query.isFetching}
        onClick={() => void query.refetch()}
      >
        {query.isError ? "重试垫资估算" : "刷新垫资估算"}
      </Button>
    </section>
  );
}

export function FundingEstimate({
  scope,
  orderId,
  permissions,
}: {
  scope: string;
  orderId: string;
  permissions: string[];
}) {
  if (
    !["order.read", "expense.read", "receivable.read", "profit.read"].every(
      (permission) => permissions.includes(permission),
    )
  )
    return null;
  return (
    <Estimate key={`${scope}:${orderId}`} scope={scope} orderId={orderId} />
  );
}
