import { z } from "zod";

export const shipmentConnectionSchema = z.object({
  organizationId: z.uuid("请输入有效的组织 ID"),
  accessToken: z.string().trim().min(1, "请填写隔离测试访问凭证"),
});

export const shipmentUploadSchema = z.object({
  documentType: z.enum([
    "COMMERCIAL_INVOICE",
    "SALES_CONTRACT",
    "PACKING_LIST",
    "BILL_OF_LADING",
    "CERTIFICATE_OF_ORIGIN",
    "BOOKING_CONFIRMATION",
    "OTHER",
  ]),
  files: z.custom<FileList>().superRefine((files, context) => {
    const file = files?.[0];
    if (!file || files.length !== 1) {
      context.addIssue({ code: "custom", message: "请选择一个文件" });
    } else if (file.size === 0 || file.size > 25 * 1024 * 1024) {
      context.addIssue({
        code: "custom",
        message: "文件不能为空，且不得超过 25 MB",
      });
    }
  }),
});

const optionalDate = z.union([z.literal(""), z.iso.date("请选择有效日期")]);
const line = z
  .object({ selected: z.boolean(), quantity: z.string() })
  .superRefine((value, context) => {
    if (
      value.selected &&
      (!/^\d{1,14}(\.\d{1,4})?$/.test(value.quantity) ||
        !/[1-9]/.test(value.quantity))
    ) {
      context.addIssue({
        code: "custom",
        path: ["quantity"],
        message: "请输入大于零的数量，最多四位小数",
      });
    }
  });

export const shipmentCreateSchema = z.object({
  forwarderCompanyId: z.union([
    z.literal(""),
    z.uuid("请输入有效的货代公司 ID"),
  ]),
  plannedDepartureDate: optionalDate,
  plannedArrivalDate: optionalDate,
  lines: z.record(z.string(), line).superRefine((values, context) => {
    const count = Object.values(values).filter(
      (value) => value.selected,
    ).length;
    if (count < 1 || count > 200)
      context.addIssue({ code: "custom", message: "请选择 1 至 200 项出运行" });
  }),
});
