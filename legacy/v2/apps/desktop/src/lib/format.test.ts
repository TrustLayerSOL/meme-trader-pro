import { describe, expect, it } from "vitest";
import { money, pct, price, shortMint } from "./format";

describe("format helpers", () => {
  it("formats trading values for dense cockpit panels", () => {
    expect(money(1_250_000)).toBe("$1.25M");
    expect(money(42_500)).toBe("$42.5K");
    expect(price(0.00000042)).toContain("e-");
    expect(pct(-12.345)).toBe("-12.35%");
  });

  it("shortens long Solana mints without changing short labels", () => {
    expect(shortMint("SKRbvo6Gf7GondiT3BbTfuRDPqLWei4j2Qy2NPGZhW3")).toBe("SKRbvo6G...ZhW3");
    expect(shortMint("ABC123")).toBe("ABC123");
  });
});
