import { describe, expect, it } from "vitest";
import { revisionSchema } from "./revision-schema";

const valid = {
  exchangeRate: "1.08000000",
  validUntil: "2026-10-04",
  prices: [{ value: "50.0000" }],
};
describe("quotation revision validation", () => {
  it("preserves exact decimal strings including zero prices", () => {
    expect(revisionSchema.parse(valid)).toEqual(valid);
    expect(
      revisionSchema.safeParse({ ...valid, prices: [{ value: "0.0000" }] })
        .success,
    ).toBe(true);
  });
  it.each(["0", "-1", "1e2", "1.123456789", "10000000000", "", "NaN"])(
    "rejects invalid rate %s",
    (exchangeRate) => {
      expect(revisionSchema.safeParse({ ...valid, exchangeRate }).success).toBe(
        false,
      );
    },
  );
  it.each(["-1", "1e2", "1.12345", "100000000000000", ""])(
    "rejects invalid price %s",
    (value) => {
      expect(
        revisionSchema.safeParse({ ...valid, prices: [{ value }] }).success,
      ).toBe(false);
    },
  );
  it("rejects impossible dates and missing lines", () => {
    expect(
      revisionSchema.safeParse({ ...valid, validUntil: "2026-02-30" }).success,
    ).toBe(false);
    expect(revisionSchema.safeParse({ ...valid, prices: [] }).success).toBe(
      false,
    );
  });
});
