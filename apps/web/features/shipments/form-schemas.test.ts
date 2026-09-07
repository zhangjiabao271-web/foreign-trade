import { describe, expect, it } from "vitest";
import { shipmentCreateSchema, shipmentUploadSchema } from "./form-schemas";

const base = {
  forwarderCompanyId: "",
  plannedDepartureDate: "",
  plannedArrivalDate: "",
  lines: { one: { selected: true, quantity: "99999999999999.1234" } },
};

describe("shipment create form", () => {
  it("checks the inclusive upload size bound and exact document type", () => {
    const file = new File(["evidence"], "evidence.txt", { type: "text/plain" });
    Object.defineProperty(file, "size", {
      value: 25 * 1024 * 1024,
      configurable: true,
    });
    const upload = { files: [file], documentType: "COMMERCIAL_INVOICE" };
    expect(shipmentUploadSchema.safeParse(upload).success).toBe(true);
    Object.defineProperty(file, "size", { value: 25 * 1024 * 1024 + 1 });
    expect(shipmentUploadSchema.safeParse(upload).success).toBe(false);
    expect(
      shipmentUploadSchema.safeParse({ files: [], documentType: "OTHER" })
        .success,
    ).toBe(false);
    expect(
      shipmentUploadSchema.safeParse({
        files: [new File(["ok"], "ok.txt")],
        documentType: "UNSUPPORTED",
      }).success,
    ).toBe(false);
  });
  it("preserves exact quantities and optional empty metadata", () => {
    expect(shipmentCreateSchema.parse(base)).toEqual(base);
  });
  it.each(["", "0", "0.0000", "-1", "1e3", "1.00001", "100000000000000"])(
    "rejects selected invalid quantity %s",
    (quantity) => {
      expect(
        shipmentCreateSchema.safeParse({
          ...base,
          lines: { one: { selected: true, quantity } },
        }).success,
      ).toBe(false);
    },
  );
  it("ignores unselected invalid quantities", () => {
    expect(
      shipmentCreateSchema.safeParse({
        ...base,
        lines: { ...base.lines, two: { selected: false, quantity: "" } },
      }).success,
    ).toBe(true);
  });
  it("requires 1 to 200 selected lines", () => {
    expect(shipmentCreateSchema.safeParse({ ...base, lines: {} }).success).toBe(
      false,
    );
    const lines = Object.fromEntries(
      Array.from({ length: 201 }, (_, i) => [
        String(i),
        { selected: true, quantity: "1.0000" },
      ]),
    );
    expect(shipmentCreateSchema.safeParse({ ...base, lines }).success).toBe(
      false,
    );
  });
  it("validates UUIDs and real calendar dates", () => {
    expect(
      shipmentCreateSchema.safeParse({ ...base, forwarderCompanyId: "wrong" })
        .success,
    ).toBe(false);
    expect(
      shipmentCreateSchema.safeParse({
        ...base,
        plannedDepartureDate: "2026-02-30",
      }).success,
    ).toBe(false);
    expect(
      shipmentCreateSchema.safeParse({
        ...base,
        plannedArrivalDate: "2028-02-29",
      }).success,
    ).toBe(true);
  });
});
