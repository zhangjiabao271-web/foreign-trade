export function refundDifference(expected: string, received: string): string {
  const scaled = (value: string) => {
    const [whole, fraction = ""] = value.split(".");
    return BigInt(whole!) * 10_000n + BigInt(fraction.padEnd(4, "0"));
  };
  const difference = scaled(expected) - scaled(received);
  return `${difference / 10_000n}.${(difference % 10_000n).toString().padStart(4, "0")}`;
}
