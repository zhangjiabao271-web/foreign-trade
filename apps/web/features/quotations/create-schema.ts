import { z } from "zod";

const money = z
  .string()
  .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负金额，最多四位小数");
const rate = z
  .string()
  .regex(/^\d{1,10}(\.\d{1,8})?$/, "请输入最多八位小数的汇率")
  .refine((value) => /[1-9]/.test(value), "汇率必须大于零");
const currency = z
  .string()
  .trim()
  .regex(/^[A-Za-z]{3}$/, "请输入三位币种代码");
export const quotationLineSchema = z.object({
  product_id: z.uuid("请输入有效的产品 ID"),
  quantity: money.refine((value) => /[1-9]/.test(value), "数量必须大于零"),
  unit_price: money,
  unit_cost: z.union([z.literal(""), money]),
  cost_currency: z.union([z.literal(""), currency]),
  cost_exchange_rate: rate,
  tax_amount: money,
  freight_amount: money,
  allocated_cost: money,
});
export const quotationCreateSchema = z.object({
  inquiryId: z.uuid("请输入有效的询盘 ID"),
  currency,
  baseCurrency: currency,
  exchangeRate: rate,
  validUntil: z.iso.date("请选择有效日期"),
  paymentTerms: z.string(),
  deliveryTerms: z.string(),
  items: z
    .array(quotationLineSchema)
    .min(1, "请添加报价行")
    .max(100, "最多 100 行"),
});
