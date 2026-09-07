import { z } from "zod";

const amount = z
  .string()
  .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负数，最多四位小数");
const positiveAmount = amount.refine(
  (value) => /[1-9]/.test(value),
  "请输入大于零的数量",
);

export const orderCreateSchema = z.object({
  quotationId: z.uuid("请输入有效的已接受报价 ID"),
  depositRate: z
    .string()
    .regex(
      /^(?:0(?:\.\d{1,4})?|1(?:\.0{1,4})?)$/,
      "定金比例须为 0 到 1，最多四位小数",
    ),
  depositDueDate: z.union([z.literal(""), z.iso.date("请选择有效日期")]),
});

export const purchaseCreateSchema = z.object({
  supplierCompanyId: z.uuid("请输入有效的供应商公司 ID"),
  currencyCode: z.string().regex(/^[A-Za-z]{3}$/, "请输入三位币种代码"),
  exchangeRate: z
    .string()
    .regex(/^\d{1,10}(\.\d{1,8})?$/, "请输入正汇率，最多八位小数")
    .refine((value) => /[1-9]/.test(value), "汇率须大于零"),
  lines: z
    .array(z.object({ quantity: positiveAmount, unitCost: amount }))
    .min(1, "至少需要一项采购行")
    .max(100, "最多支持 100 项采购行"),
});

export const purchaseConfirmSchema = z.object({
  supplierReference: z.string().max(120, "供应商确认号最多 120 个字符"),
  expectedDeliveryDate: z.iso.date("请选择有效的预计交付日"),
});
