import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TokenDetail } from "./TokenDetail";
import type { PositionDetailPayload } from "../lib/api";

describe("TokenDetail", () => {
  it("renders a single empty state instead of fake unknown diagnostics without detail", () => {
    const markup = renderToStaticMarkup(<TokenDetail detail={null} />);

    expect(markup).toContain("No token detail selected");
    expect(markup).not.toContain("Token Mechanics");
  });

  it("renders selected-token data sources and mixed-field warning", () => {
    const detail: PositionDetailPayload = {
      mint: "Mint111",
      snapshot_count: 1,
      position_source: "paper_trades_json",
      position_source_detail: "data/paper_trades.json",
      snapshot_source: "sqlite_token_snapshots",
      snapshot_source_detail: "data/memetrader.db:token_snapshots",
      mixed_market_fields: true,
      mixed_market_fields_note: "position market fields come from JSON while snapshots come from SQLite",
      latest_snapshot: {
        market_info: { market_cap: 12345 },
      },
    };

    const markup = renderToStaticMarkup(<TokenDetail detail={detail} />);

    expect(markup).toContain("Data Sources");
    expect(markup).toContain("paper_trades_json");
    expect(markup).toContain("data/paper_trades.json");
    expect(markup).toContain("sqlite_token_snapshots");
    expect(markup).toContain("data/memetrader.db:token_snapshots");
    expect(markup).toContain("Mixed Fields");
    expect(markup).toContain("position market fields come from JSON");
  });
});
