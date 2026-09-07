import { describe, expect, it } from "vitest";
import {
  orderCreateSchema,
  purchaseCreateSchema,
  purchaseConfirmSchema,
} from "./form-schemas";

const id = "00000000-0000-4000-8000-000000000001";
describe("Order form validation", () => {
  it("limits deposit ratios without changing decimal strings", () => {
    for (const depositRate of ["0", "0.0000", "0.1234", "1.0000"]) {
      expect(
        orderCreateSchema.parse({
          quotationId: id,
          depositRate,
          depositDueDate: "",
        }).depositRate,
      ).toBe(depositRate);
    }
    for (const depositRate of ["-1", "1.0001", "0.12345", "1e-4"]) {
      expect(
        orderCreateSchema.safeParse({
          quotationId: id,
          depositRate,
          depositDueDate: "",
        }).success,
      ).toBe(false);
    }
  });
  it("preserves numeric precision and rejects invalid purchase inputs", () => {
    const data = {
      supplierCompanyId: id,
      currencyCode: "CNY",
      exchangeRate: "0.12345678",
      lines: [{ quantity: "1.2345", unitCost: "12345678901234.5678" }],
    };
    expect(purchaseCreateSchema.parse(data)).toEqual(data);
    for (const exchangeRate of [
      "0.00000000",
      "-1",
      "0.123456789",
      "Infinity",
    ]) {
      expect(
        purchaseCreateSchema.safeParse({ ...data, exchangeRate }).success,
      ).toBe(false);
    }
    for (const quantity of ["0.0000", "1.12345", "-1", "1e2"]) {
      expect(
        purchaseCreateSchema.safeParse({
          ...data,
          lines: [{ quantity, unitCost: "0.0000" }],
        }).success,
      ).toBe(false);
    }
    expect(purchaseCreateSchema.safeParse({ ...data, lines: [] }).success).toBe(
      false,
    );
    expect(
      purchaseCreateSchema.safeParse({ ...data, currencyCode: "EU" }).success,
    ).toBe(false);
  });
  it("checks actual calendar dates and supplier reference length", () => {
    expect(
      purchaseConfirmSchema.safeParse({
        supplierReference: "",
        expectedDeliveryDate: "2026-02-29",
      }).success,
    ).toBe(false);
    expect(
      purchaseConfirmSchema.safeParse({
        supplierReference: "x".repeat(121),
        expectedDeliveryDate: "2026-09-06",
      }).success,
    ).toBe(false);
    expect(
      purchaseConfirmSchema.parse({
        supplierReference: "PO-1",
        expectedDeliveryDate: "2026-09-06",
      }).supplierReference,
    ).toBe("PO-1");
  });
});
