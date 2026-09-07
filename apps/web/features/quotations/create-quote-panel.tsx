"use client";

import { useFieldArray, useForm } from "react-hook-form";
import { useRef } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { quotationCreateSchema, quotationLineSchema } from "./create-schema";
import { useCreateQuotation } from "./api";
import { ApiClientError } from "@trade-workbench/api-client";
import { InquiryPicker } from "./inquiry-picker";

const emptyLine = (
  canReadCosts: boolean,
): z.infer<typeof quotationLineSchema> => ({
  product_id: "",
  quantity: "1.0000",
  unit_price: "0.0000",
  unit_cost: "",
  cost_currency: "",
  cost_exchange_rate: canReadCosts ? "" : "1.00000000",
  tax_amount: "0.0000",
  freight_amount: "0.0000",
  allocated_cost: "0.0000",
});
const headerFields = [
  { key: "inquiryId", label: "询盘 ID *", type: "text" },
  { key: "currency", label: "报价币种 *", type: "text" },
  { key: "baseCurrency", label: "基准币种 *", type: "text" },
  { key: "exchangeRate", label: "基准汇率 *", type: "text" },
  { key: "validUntil", label: "有效期 *", type: "date" },
  { key: "paymentTerms", label: "付款条件", type: "text" },
  { key: "deliveryTerms", label: "交付条款", type: "text" },
] as const;
const lineFields = [
  { key: "product_id", label: "产品 ID *" },
  { key: "quantity", label: "数量 *" },
  { key: "unit_price", label: "销售单价 *" },
  { key: "unit_cost", label: "成本单价" },
  { key: "cost_currency", label: "成本币种" },
  { key: "cost_exchange_rate", label: "成本换算率 *" },
  { key: "tax_amount", label: "税费" },
  { key: "freight_amount", label: "运费" },
  { key: "allocated_cost", label: "额外成本" },
] as const;

export function CreateQuotePanel({
  onClose,
  onCreated,
  canReadCosts = false,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
  canReadCosts?: boolean;
}) {
  const mutation = useCreateQuotation();
  const retry = useRef<{ payload: string; key: string } | null>(null);
  const submitting = useRef(false);
  const form = useForm<z.infer<typeof quotationCreateSchema>>({
    resolver: zodResolver(quotationCreateSchema),
    mode: "onBlur",
    defaultValues: {
      inquiryId: "",
      currency: "USD",
      baseCurrency: "CNY",
      exchangeRate: "7.10000000",
      validUntil: "",
      paymentTerms: "",
      deliveryTerms: "",
      items: [emptyLine(canReadCosts)],
    },
  });
  const lines = useFieldArray({ control: form.control, name: "items" });
  return (
    <section className="quote-form-panel" aria-labelledby="new-quote-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">商业快照</p>
          <h2 id="new-quote-title">创建报价 V1</h2>
        </div>
        <button
          className="quiet-button"
          type="button"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          取消
        </button>
      </div>
      <form
        noValidate
        aria-busy={mutation.isPending}
        onSubmit={(event) => {
          void form.handleSubmit(async (data) => {
            if (submitting.current) return;
            submitting.current = true;
            const body = {
              inquiry_id: data.inquiryId,
              currency_code: data.currency.toUpperCase(),
              base_currency_code: data.baseCurrency.toUpperCase(),
              exchange_rate: data.exchangeRate,
              valid_until: data.validUntil,
              payment_terms: data.paymentTerms || null,
              delivery_terms: data.deliveryTerms || null,
              items: data.items.map((line) => ({
                product_id: line.product_id,
                quantity: line.quantity,
                unit_price: line.unit_price,
                tax_amount: line.tax_amount,
                freight_amount: line.freight_amount,
                ...(canReadCosts
                  ? {
                      unit_cost: line.unit_cost || null,
                      cost_currency: line.cost_currency.toUpperCase() || null,
                      cost_exchange_rate: line.cost_exchange_rate,
                      allocated_cost: line.allocated_cost,
                    }
                  : {}),
              })),
            };
            const payload = JSON.stringify(body);
            if (retry.current?.payload !== payload) {
              retry.current = { payload, key: crypto.randomUUID() };
            }
            try {
              const quote = await mutation.mutateAsync({
                body,
                key: retry.current.key,
              });
              onCreated(quote.id);
            } catch {
              // Keep the unchanged command identity when the response is uncertain.
            } finally {
              submitting.current = false;
            }
          })(event);
        }}
      >
        <InquiryPicker
          disabled={mutation.isPending}
          onSelect={(id) => {
            form.setValue("inquiryId", id, {
              shouldDirty: true,
              shouldValidate: true,
            });
            form.setFocus("inquiryId");
          }}
        />
        {headerFields.map(({ key, label, type }) => (
          <label key={key}>
            {label}
            <input
              {...form.register(key)}
              type={type}
              aria-label={label}
              inputMode={key === "exchangeRate" ? "decimal" : undefined}
              disabled={mutation.isPending}
              aria-invalid={Boolean(form.formState.errors[key])}
              aria-describedby={`create-quote-${key}-error`}
            />
            {form.formState.errors[key] && (
              <span
                id={`create-quote-${key}-error`}
                className="form-error"
                role="alert"
              >
                {form.formState.errors[key]?.message}
              </span>
            )}
          </label>
        ))}
        <fieldset
          className="quote-lines field-span-full"
          disabled={mutation.isPending}
        >
          <legend>报价行</legend>
          {!canReadCosts && (
            <p>
              成本由后端继承；涉及尚未准备的跨币种成本时，请经理先建立报价草稿。
            </p>
          )}
          {lines.fields.map((line, index) => (
            <div className="quote-line-editor" key={line.id}>
              {lineFields
                .filter(
                  ({ key }) =>
                    canReadCosts ||
                    ![
                      "unit_cost",
                      "cost_currency",
                      "cost_exchange_rate",
                      "allocated_cost",
                    ].includes(key),
                )
                .map(({ key, label }) => (
                  <label key={key}>
                    {label}
                    <input
                      {...form.register(`items.${index}.${key}`)}
                      aria-label={label}
                      inputMode={
                        key === "product_id" || key === "cost_currency"
                          ? undefined
                          : "decimal"
                      }
                      aria-invalid={Boolean(
                        form.formState.errors.items?.[index]?.[key],
                      )}
                      aria-describedby={`create-line-${index}-${key}-error`}
                      placeholder={
                        key === "unit_cost"
                          ? "默认产品成本"
                          : key === "cost_currency"
                            ? "默认产品币种"
                            : undefined
                      }
                    />
                    {form.formState.errors.items?.[index]?.[key] && (
                      <span
                        id={`create-line-${index}-${key}-error`}
                        className="form-error"
                        role="alert"
                      >
                        {form.formState.errors.items[index]?.[key]?.message}
                      </span>
                    )}
                  </label>
                ))}
              {lines.fields.length > 1 && (
                <button
                  className="quiet-button"
                  type="button"
                  onClick={() => lines.remove(index)}
                >
                  移除此行
                </button>
              )}
            </div>
          ))}
          <button
            className="secondary-button"
            type="button"
            disabled={lines.fields.length >= 100}
            onClick={() => lines.append(emptyLine(canReadCosts))}
          >
            添加一行
          </button>
        </fieldset>
        {form.formState.errors.items?.message && (
          <p role="alert" className="form-error">
            {form.formState.errors.items.message}
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="form-error field-span-full">
            {mutation.error instanceof ApiClientError
              ? `${mutation.error.problem.detail}（${mutation.error.problem.code}）`
              : "创建结果未确认。保持输入不变再次提交可找回原报价。"}
          </p>
        )}
        <p className="field-span-full">
          结果未确认时可保持输入不变重试；修改输入会视为新请求。关闭或刷新页面后，请先核对报价队列。
        </p>
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在计算并冻结…" : "创建报价 V1"}
        </button>
      </form>
    </section>
  );
}
