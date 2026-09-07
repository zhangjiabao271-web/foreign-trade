import { z } from "zod";

export const revisionSchema = z.object({
  exchangeRate: z
    .string()
    .regex(/^\d{1,10}(\.\d{1,8})?$/, "请输入最多八位小数的汇率")
    .refine((value) => /[1-9]/.test(value), "汇率必须大于零"),
  validUntil: z.iso.date("请选择有效日期"),
  prices: z
    .array(
      z.object({
        value: z
          .string()
          .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负单价，最多四位小数"),
      }),
    )
    .min(1, "报价至少需要一行商品")
    .max(100),
});
