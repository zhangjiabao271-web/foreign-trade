export function sumCommitments(
  values: (string | null | undefined)[],
): string | null {
  if (values.some((value) => value == null)) return null;
  const total = values.reduce((sum, value) => {
    if (value == null) return sum;
    if (!/^\d+(\.\d{1,4})?$/.test(value))
      throw new Error("Invalid commitment amount");
    const [whole, fraction = ""] = value.split(".");
    return sum + BigInt(whole!) * 10_000n + BigInt(fraction.padEnd(4, "0"));
  }, 0n);
  return `${total / 10_000n}.${(total % 10_000n).toString().padStart(4, "0")}`;
}
