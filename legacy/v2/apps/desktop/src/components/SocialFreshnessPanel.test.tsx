import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SocialFreshnessPanel } from "./SocialFreshnessPanel";
import type { SocialFreshnessPayload } from "../lib/api";

describe("SocialFreshnessPanel", () => {
  it("renders source and collector staleness without trade-action language", () => {
    const freshness: SocialFreshnessPayload = {
      generated_at: 123,
      mode: "SOCIAL_FRESHNESS_READ_ONLY",
      live_execution_locked: true,
      overall: "WARN",
      counts: { FRESH: 1, STALE: 1, NOT_CONFIGURED: 1 },
      rows: [
        {
          source: "manual_social_import",
          label: "Manual Social Import",
          status: "STALE",
          age: "2.0h",
          event_count: 2,
          detail: "latest manual import is stale",
        },
        {
          source: "reddit",
          label: "Reddit Collector",
          status: "NOT_CONFIGURED",
          age: "N/A",
          event_count: 0,
          detail: "collector not configured",
        },
      ],
    };

    const markup = renderToStaticMarkup(<SocialFreshnessPanel freshness={freshness} />);

    expect(markup).toContain("Social Freshness");
    expect(markup).toContain("WARN");
    expect(markup).toContain("Manual Social Import");
    expect(markup).toContain("STALE");
    expect(markup).toContain("Reddit Collector");
    expect(markup).toContain("NOT_CONFIGURED");
    expect(markup).not.toContain("buy");
    expect(markup).not.toContain("trade triggered");
  });
});
