import { shortMint } from "./format";

export type DecisionFilter = "all" | "bought" | "skipped" | "exploration" | "quote_failed" | "hard_risk" | "social" | "wallet";

export type DecisionRecord = {
  decision_id?: string;
  created_at?: number | string | null;
  updated_at?: number | string | null;
  mint?: string;
  signal_type?: string | null;
  final_action?: string | null;
  action_reason?: string | null;
  paper_lane?: string | null;
  total_score?: number | string | null;
  threshold?: number | string | null;
  risk_label?: string | null;
  buy_quote_pass?: boolean | null;
  sell_quote_pass?: boolean | null;
  wallet_count?: number | string | null;
  paper_result?: Record<string, unknown> | null;
  payload?: {
    inputs?: {
      wallets?: string[];
      wallet_count?: number | string | null;
      social_match?: {
        matched?: boolean;
        reason?: string | null;
      };
    };
    rule_outcomes?: {
      risk?: {
        hard_block?: boolean;
        hard_block_reason?: string | null;
        warnings?: string[];
      };
      scoring?: {
        reasons?: string[];
      };
    };
    quotes?: {
      buy?: { reason?: string | null; route?: string | null; price_impact_pct?: number | string | null };
      sell?: { reason?: string | null; route?: string | null; price_impact_pct?: number | string | null };
    };
    social_matched?: boolean;
  } & Record<string, unknown>;
} & Record<string, unknown>;

export type DecisionLedgerPayload = {
  generated_at?: number;
  source?: string;
  live_execution_locked?: boolean;
  count?: number;
  filter?: string;
  lane?: string | null;
  items: DecisionRecord[];
};

export function decisionMatchesFilter(decision: DecisionRecord, filter: DecisionFilter): boolean {
  if (!filter || filter === "all") return true;
  const action = String(decision.final_action || "").toLowerCase();
  const payload = decision.payload || {};
  const inputs = payload.inputs || {};
  const risk = payload.rule_outcomes?.risk || {};

  if (filter === "bought") return action.includes("opened") || action.includes("open_attempt");
  if (filter === "skipped") return action.includes("skip") || action.includes("blocked") || action === "runtime_skip";
  if (filter === "exploration") return decision.paper_lane === "exploration";
  if (filter === "quote_failed") return decision.buy_quote_pass === false || decision.sell_quote_pass === false;
  if (filter === "hard_risk") return Boolean(risk.hard_block || decision.risk_label === "DANGER" || decision.risk_label === "EMERGENCY");
  if (filter === "social") return Boolean(inputs.social_match?.matched || payload.social_matched);
  if (filter === "wallet") return Boolean((inputs.wallets || []).length) || Number(inputs.wallet_count || decision.wallet_count || 0) > 0;
  return true;
}

export function filteredDecisions(rows: DecisionRecord[], filter: DecisionFilter): DecisionRecord[] {
  return rows.filter((decision) => decisionMatchesFilter(decision, filter));
}

export function selectedDecisionForFilter(rows: DecisionRecord[], selectedDecisionId: string, filter: DecisionFilter): DecisionRecord | null {
  const visible = filteredDecisions(rows, filter);
  return visible.find((decision) => decision.decision_id === selectedDecisionId) || visible[0] || null;
}

export function decisionQuotePair(decision: DecisionRecord): string {
  const buy = decision.buy_quote_pass === true ? "B+" : decision.buy_quote_pass === false ? "B-" : "B?";
  const sell = decision.sell_quote_pass === true ? "S+" : decision.sell_quote_pass === false ? "S-" : "S?";
  return `${buy}/${sell}`;
}

export function decisionWalletSummary(decision: DecisionRecord): string {
  const wallets = (decision.payload?.inputs?.wallets || []).filter(Boolean);
  return wallets.length ? wallets.map((wallet) => shortMint(wallet)).join(", ") : "-";
}

export function decisionSocialSummary(decision: DecisionRecord): string {
  const social = decision.payload?.inputs?.social_match;
  if (social?.reason) return social.reason;
  if (social?.matched || decision.payload?.social_matched) return "matched";
  return "-";
}

export function decisionRiskNotes(decision: DecisionRecord): string {
  const risk = decision.payload?.rule_outcomes?.risk;
  return (risk?.warnings || []).slice(0, 4).join("; ") || risk?.hard_block_reason || "-";
}

export function decisionScoreNotes(decision: DecisionRecord): string {
  return (decision.payload?.rule_outcomes?.scoring?.reasons || []).slice(0, 4).join("; ") || "-";
}

export function decisionQuoteReason(decision: DecisionRecord, side: "buy" | "sell"): string {
  const quote = decision.payload?.quotes?.[side];
  return quote?.reason || String(side === "buy" ? decision.buy_quote_pass ?? "-" : decision.sell_quote_pass ?? "-");
}
