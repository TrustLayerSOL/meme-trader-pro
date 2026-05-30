import { describe, expect, it } from "vitest";
import { candidateFeedApiPath, candidateWalletsApiPath, decisionLedgerApiPath, desktopApiUrl, eventFeedApiPath, fetchJson, importSocialPost, OVERVIEW_REFRESH_MS, postJson, protectedAmountApiPath, protectedTokenApiPath, SELECTED_TOKEN_REFRESH_MS, setDesktopApiToken, socialImportApiPath, tokenApiPaths, walletDetailApiPath, walletLifecycleApiPath, walletReviewApplyApiPath, walletReviewDecisionApiPath, winnerPatternsApiPath } from "./api";

describe("desktop API helper", () => {
  it("builds localhost API URLs without touching live execution routes", () => {
    const url = desktopApiUrl("/api/positions");

    expect(url.toString()).toBe("http://127.0.0.1:8765/api/positions");
  });

  it("rejects non-api paths", async () => {
    await expect(fetchJson("/buy")).rejects.toThrow("local /api paths");
  });

  it("builds encoded selected-token read-only paths", () => {
    const paths = tokenApiPaths("Mint / With Spaces", "liquidity");

    expect(paths.detail).toBe("/api/positions/Mint%20%2F%20With%20Spaces");
    expect(paths.candles).toBe("/api/candles?mint=Mint%20%2F%20With%20Spaces&limit=240&metric=liquidity&interval=1");
    expect(paths.snapshots).toBe("/api/tokens/Mint%20%2F%20With%20Spaces/snapshots?limit=25");
  });

  it("builds selected-token candle paths with the requested interval", () => {
    const paths = tokenApiPaths("Mint111", "price", 30);

    expect(paths.candles).toBe("/api/candles?mint=Mint111&limit=240&metric=price&interval=30");
  });

  it("allows system readiness reads", () => {
    expect(desktopApiUrl("/api/readiness").toString()).toBe("http://127.0.0.1:8765/api/readiness");
  });

  it("allows data freshness reads", () => {
    expect(desktopApiUrl("/api/freshness").toString()).toBe("http://127.0.0.1:8765/api/freshness");
  });

  it("allows paper trade replay reads", () => {
    expect(desktopApiUrl("/api/trades").toString()).toBe("http://127.0.0.1:8765/api/trades");
  });

  it("builds the canonical decision ledger read-only path", () => {
    expect(decisionLedgerApiPath()).toBe("/api/decisions?limit=80");
    expect(decisionLedgerApiPath(24)).toBe("/api/decisions?limit=24");
    expect(desktopApiUrl(decisionLedgerApiPath(24)).toString()).toBe("http://127.0.0.1:8765/api/decisions?limit=24");
  });

  it("allows wallet intelligence reads", () => {
    expect(desktopApiUrl("/api/wallets").toString()).toBe("http://127.0.0.1:8765/api/wallets");
  });

  it("builds the live candidate feed read-only path", () => {
    expect(candidateFeedApiPath()).toBe("/api/candidates?limit=80");
    expect(candidateFeedApiPath(24)).toBe("/api/candidates?limit=24");
    expect(desktopApiUrl(candidateFeedApiPath(24)).toString()).toBe("http://127.0.0.1:8765/api/candidates?limit=24");
  });

  it("builds the live wallet event feed read-only path", () => {
    expect(eventFeedApiPath()).toBe("/api/events?limit=120");
    expect(eventFeedApiPath(36)).toBe("/api/events?limit=36");
    expect(desktopApiUrl(eventFeedApiPath(36)).toString()).toBe("http://127.0.0.1:8765/api/events?limit=36");
  });

  it("builds encoded wallet detail read-only paths", () => {
    expect(walletDetailApiPath("Wallet / Test")).toBe("/api/wallets/Wallet%20%2F%20Test?limit=40");
  });

  it("builds the candidate wallet review read-only path", () => {
    expect(candidateWalletsApiPath()).toBe("/api/candidate-wallets?limit=80");
    expect(candidateWalletsApiPath(24)).toBe("/api/candidate-wallets?limit=24");
    expect(desktopApiUrl(candidateWalletsApiPath(24)).toString()).toBe("http://127.0.0.1:8765/api/candidate-wallets?limit=24");
  });

  it("builds the wallet lifecycle read-only path", () => {
    expect(walletLifecycleApiPath()).toBe("/api/wallet-lifecycle?limit=80");
    expect(walletLifecycleApiPath(24)).toBe("/api/wallet-lifecycle?limit=24");
    expect(desktopApiUrl(walletLifecycleApiPath(24)).toString()).toBe("http://127.0.0.1:8765/api/wallet-lifecycle?limit=24");
  });

  it("builds the wallet review decision metadata endpoint", () => {
    expect(walletReviewDecisionApiPath()).toBe("/api/wallet-review-decision");
    expect(desktopApiUrl(walletReviewDecisionApiPath()).toString()).toBe("http://127.0.0.1:8765/api/wallet-review-decision");
  });

  it("builds the wallet review apply preview endpoint", () => {
    expect(walletReviewApplyApiPath()).toBe("/api/wallet-review-apply");
    expect(desktopApiUrl(walletReviewApplyApiPath()).toString()).toBe("http://127.0.0.1:8765/api/wallet-review-apply");
  });

  it("builds the social import endpoint", () => {
    expect(socialImportApiPath()).toBe("/api/social/import");
    expect(desktopApiUrl(socialImportApiPath()).toString()).toBe("http://127.0.0.1:8765/api/social/import");
  });

  it("allows read-only operator config and logs reads", () => {
    expect(desktopApiUrl("/api/operator-config").toString()).toBe("http://127.0.0.1:8765/api/operator-config");
    expect(desktopApiUrl("/api/logs?limit=40").toString()).toBe("http://127.0.0.1:8765/api/logs?limit=40");
  });

  it("builds the protected amount metadata endpoint", () => {
    expect(protectedAmountApiPath()).toBe("/api/watchlist/protected-amount");
    expect(desktopApiUrl(protectedAmountApiPath()).toString()).toBe("http://127.0.0.1:8765/api/watchlist/protected-amount");
  });

  it("builds the protected token metadata endpoint", () => {
    expect(protectedTokenApiPath()).toBe("/api/watchlist/protected-token");
    expect(desktopApiUrl(protectedTokenApiPath()).toString()).toBe("http://127.0.0.1:8765/api/watchlist/protected-token");
  });

  it("builds the winner pattern review endpoint", () => {
    expect(winnerPatternsApiPath()).toBe("/api/winner-patterns");
    expect(desktopApiUrl(winnerPatternsApiPath()).toString()).toBe("http://127.0.0.1:8765/api/winner-patterns");
  });

  it("sends the desktop session token on metadata posts", async () => {
    const originalFetch = globalThis.fetch;
    const calls: RequestInit[] = [];
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(init || {});
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    try {
      setDesktopApiToken("token-123");
      await postJson("/api/wallet-review-decision", { wallet: "Wallet111", decision: "hold" });
      expect((calls[0].headers as Record<string, string>)["X-MemeTraderPro-Token"]).toBe("token-123");
    } finally {
      setDesktopApiToken(null);
      globalThis.fetch = originalFetch;
    }
  });

  it("posts social imports with selected-token context", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; init: RequestInit }> = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init: init || {} });
      return new Response(JSON.stringify({ imported: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    try {
      const response = await importSocialPost({
        mint: "Mint111",
        account: "@watcher",
        text: "Fresh volume spike",
      });

      expect(response.imported).toBe(true);
      expect(calls[0].url).toBe("http://127.0.0.1:8765/api/social/import");
      expect(calls[0].init.method).toBe("POST");
      expect(calls[0].init.body).toBe(JSON.stringify({
        mint: "Mint111",
        account: "@watcher",
        text: "Fresh volume spike",
      }));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps selected-token refresh faster than broad overview refresh", () => {
    expect(SELECTED_TOKEN_REFRESH_MS).toBe(1000);
    expect(OVERVIEW_REFRESH_MS).toBeGreaterThan(SELECTED_TOKEN_REFRESH_MS);
  });
});
