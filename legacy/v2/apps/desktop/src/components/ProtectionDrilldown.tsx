import { useEffect, useState, type FormEvent } from "react";
import { saveProtectedAmount, saveProtectedToken, type PositionDetailPayload, type ProtectionSummary, type WatchlistPayload, type WatchlistItem } from "../lib/api";
import { money, pct, price, shortMint } from "../lib/format";

type Props = {
  selectedMint: string;
  detail: PositionDetailPayload | null;
  watchlist: WatchlistPayload | null;
  onSelectMint: (mint: string) => void;
  onProtectedAmountSaved: (item: WatchlistItem) => void;
};

export function ProtectionDrilldown({ selectedMint, detail, watchlist, onSelectMint, onProtectedAmountSaved }: Props) {
  const items = watchlist?.items || [];
  const selected = items.find((item) => itemMint(item) === selectedMint) || items[0];
  const protection = detail?.protection;
  const readinessRows = buildExitReadiness(selected, protection);
  const reasons = [
    ...(selected?.token_mechanics_reasons || []),
    ...(protection?.reasons || []),
    selected?.reason,
  ].filter(Boolean).slice(0, 8) as string[];

  return (
    <section className="protection-drilldown">
      <div className="panel protected-list">
        <h2>Protected Tokens</h2>
        {items.length ? items.map((item) => (
          <button
            className={itemMint(item) === selectedMint ? "protected-row active" : "protected-row"}
            key={itemMint(item)}
            onClick={() => onSelectMint(itemMint(item))}
          >
            <div>
              <strong>{itemLabel(item)}</strong>
              <small>{shortMint(itemMint(item))}</small>
            </div>
            <span>{item.risk_level || item.alert_level || item.status || "UNKNOWN"}</span>
          </button>
        )) : <p className="muted">No manual watchlist entries loaded.</p>}
      </div>

      <div className="panel protection-main">
        <h2>Protection Drilldown</h2>
        <div className="protection-title-row">
          <div>
            <strong>{selected ? itemLabel(selected) : detail?.position?.label || "No token selected"}</strong>
            <small>{selected ? shortMint(itemMint(selected)) : shortMint(selectedMint)}</small>
          </div>
          <span className="danger-pill">{selected?.risk_level || selected?.alert_level || protection?.risk_level || "UNKNOWN"}</span>
        </div>

        <div className="protection-metric-grid">
          <Metric label="Price" value={price(selected?.current_price ?? detail?.position?.price)} />
          <Metric label="Liquidity" value={money(selected?.current_liquidity ?? detail?.position?.liquidity)} />
          <Metric label="Price From Peak" value={pct(selected?.price_from_peak_pct ?? protection?.price_from_peak_pct)} tone="bad" />
          <Metric label="Liquidity From Peak" value={pct(selected?.liquidity_from_peak_pct ?? protection?.liquidity_from_peak_pct)} tone="bad" />
          <Metric label="Quote" value={selected?.quote_status || protection?.quote_status || "not_checked"} />
          <Metric label="Sell Plan" value={sellPlan(selected, protection?.suggested_sell_pct)} />
          <Metric label="Amount" value={amountLabel(selected, protection)} />
          <Metric label="Amount Source" value={selected?.token_amount_source || protection?.token_amount_source || "missing"} />
          <Metric label="Holders" value={selected?.holder_count ?? detail?.latest_snapshot?.holder_count ?? "-"} />
          <Metric label="Top 10" value={pct(selected?.holder_top_10_pct ?? detail?.latest_snapshot?.holder_top_10_pct)} />
        </div>
        <p className="muted">
          {amountDetail(selected, protection)}
        </p>
        {selected?.test_amount || protection?.test_amount ? <p className="note danger-note">{selected?.amount_safety_note || protection?.amount_safety_note || "Test amount only. Does not represent a wallet balance or owned position."}</p> : null}

        <div className="exit-readiness">
          <h3>Exit Readiness</h3>
          {readinessRows.map((row) => (
            <div className="check-row" key={row.label}>
              <span className={`check-dot ${row.tone}`} />
              <div>
                <strong>{row.label}</strong>
                <small>{row.detail}</small>
              </div>
              <em>{row.status}</em>
            </div>
          ))}
        </div>
      </div>

      <div className="panel protection-side">
        <h2>Safety State</h2>
        <AddProtectedTokenForm onSaved={(item) => {
          onProtectedAmountSaved(item);
          onSelectMint(itemMint(item));
        }} />
        <div className="lock-strip">
          <span>Live Action</span>
          <strong>LOCKED</strong>
        </div>
        <div className="lock-strip">
          <span>Auto Sell</span>
          <strong>{selected?.auto_sell || protection?.auto_sell_enabled ? "BLOCKED" : "OFF"}</strong>
        </div>
        <div className="lock-strip">
          <span>Mode</span>
          <strong>{selected?.alert_only === false ? "PROTECTED" : "ALERT ONLY"}</strong>
        </div>
        <div className="lock-strip">
          <span>Token Mechanics</span>
          <strong>{selected?.token_mechanics_risk || protection?.token_mechanics_risk || "UNKNOWN"}</strong>
        </div>
        <p className="muted">{selected?.token_standard || protection?.token_standard || "Token standard unknown"} | {(selected?.token_extensions || protection?.token_extensions || []).join(", ") || "no extension data"}</p>
        {reasons.length ? reasons.map((reason) => <p className="note" key={reason}>{reason}</p>) : <p className="muted">No protection reasons recorded.</p>}
        <ProtectedAmountEditor selected={selected} onSaved={onProtectedAmountSaved} />
      </div>
    </section>
  );
}

function AddProtectedTokenForm({ onSaved }: { onSaved: (item: WatchlistItem) => void }) {
  const [mint, setMint] = useState("");
  const [wallet, setWallet] = useState("");
  const [amount, setAmount] = useState("");
  const [decimals, setDecimals] = useState("6");
  const [raw, setRaw] = useState("");
  const [testAmount, setTestAmount] = useState(true);
  const [exitPriority, setExitPriority] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus("");
    const cleanMint = mint.trim();
    if (!cleanMint) {
      setError("Token mint / CA is required.");
      return;
    }
    setSaving(true);
    try {
      const response = await saveProtectedToken({
        mint: cleanMint,
        wallet: wallet.trim() || undefined,
        amount: amount.trim() || undefined,
        decimals: decimals.trim() || undefined,
        raw: raw.trim() || undefined,
        test: testAmount,
        alert_only: true,
        external_position: true,
        exit_priority: exitPriority || undefined,
      });
      onSaved(response.item);
      setStatus(response.detail || "Protected token added.");
      setMint("");
      setWallet("");
      setAmount("");
      setRaw("");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to add protected token.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="protected-editor add-protected-token" onSubmit={submit}>
      <h3>Add Protected Token</h3>
      <label>
        <span>Token Mint / CA</span>
        <input value={mint} onChange={(event) => setMint(event.target.value)} placeholder="Paste contract address" />
      </label>
      <label>
        <span>Your Wallet</span>
        <input value={wallet} onChange={(event) => setWallet(event.target.value)} placeholder="optional" />
      </label>
      <label>
        <span>Token Amount</span>
        <input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="optional" inputMode="decimal" />
      </label>
      <label>
        <span>Decimals</span>
        <input value={decimals} onChange={(event) => setDecimals(event.target.value)} placeholder="6" inputMode="numeric" />
      </label>
      <label>
        <span>Raw Amount</span>
        <input value={raw} onChange={(event) => setRaw(event.target.value)} placeholder="optional" inputMode="numeric" />
      </label>
      <label>
        <span>Exit Priority</span>
        <select value={exitPriority} onChange={(event) => setExitPriority(event.target.value)}>
          <option value="">normal</option>
          <option value="immediate">immediate</option>
        </select>
      </label>
      <label className="toggle-line">
        <input type="checkbox" checked={testAmount} onChange={(event) => setTestAmount(event.target.checked)} />
        <span>Mark amount as test/simulated</span>
      </label>
      <button type="submit" disabled={saving}>{saving ? "Adding" : "Add / Update Watch"}</button>
      {status ? <p className="note good-note">{status}</p> : null}
      {error ? <p className="note danger-note">{error}</p> : null}
      <p className="muted">Watch and alert only. This cannot sell or enable auto-sell.</p>
    </form>
  );
}

function ProtectedAmountEditor({ selected, onSaved }: { selected?: WatchlistItem; onSaved: (item: WatchlistItem) => void }) {
  const mint = selected ? itemMint(selected) : "";
  const [amount, setAmount] = useState("");
  const [decimals, setDecimals] = useState("");
  const [raw, setRaw] = useState("");
  const [testAmount, setTestAmount] = useState(true);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setAmount(selected?.token_amount ? String(selected.token_amount) : "");
    setDecimals(selected?.token_decimals != null ? String(selected.token_decimals) : "");
    setRaw("");
    setTestAmount(selected?.test_amount ?? selected?.token_amount_source !== "operator_manual");
    setStatus("");
    setError("");
  }, [mint, selected?.token_amount, selected?.token_decimals, selected?.test_amount, selected?.token_amount_source]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus("");
    const cleanAmount = amount.trim();
    const cleanDecimals = decimals.trim();
    const cleanRaw = raw.trim();
    if (!mint) {
      setError("Select a protected token first.");
      return;
    }
    if (!cleanAmount && !cleanRaw) {
      setError("Enter a decimal amount or raw amount.");
      return;
    }
    if (cleanAmount && !cleanRaw && !cleanDecimals) {
      setError("Decimals are required when using a decimal amount.");
      return;
    }
    setSaving(true);
    try {
      const response = await saveProtectedAmount({
        mint,
        wallet: selected?.wallet || "",
        amount: cleanAmount || undefined,
        decimals: cleanDecimals || undefined,
        raw: cleanRaw || undefined,
        test: testAmount,
      });
      onSaved(response.item);
      setStatus(response.detail || "Protected amount saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save protected amount.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="protected-editor" onSubmit={submit}>
      <h3>Protected Amount</h3>
      <label>
        <span>Amount</span>
        <input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="1000" inputMode="decimal" />
      </label>
      <label>
        <span>Decimals</span>
        <input value={decimals} onChange={(event) => setDecimals(event.target.value)} placeholder="6" inputMode="numeric" />
      </label>
      <label>
        <span>Raw Amount</span>
        <input value={raw} onChange={(event) => setRaw(event.target.value)} placeholder="optional" inputMode="numeric" />
      </label>
      <label className="toggle-line">
        <input type="checkbox" checked={testAmount} onChange={(event) => setTestAmount(event.target.checked)} />
        <span>Mark as test/simulated amount</span>
      </label>
      <button type="submit" disabled={saving || !mint}>{saving ? "Saving" : "Save Amount"}</button>
      {status ? <p className="note good-note">{status}</p> : null}
      {error ? <p className="note danger-note">{error}</p> : null}
      <p className="muted">This only updates local protection metadata. It cannot buy, sell, or enable auto-sell.</p>
    </form>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: "bad" | "good" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

function itemMint(item: WatchlistItem): string {
  return item.token_mint || item.mint || "";
}

function itemLabel(item: WatchlistItem): string {
  return item.symbol || item.name || shortMint(itemMint(item)) || "protected";
}

function sellPlan(item: WatchlistItem | undefined, fallback?: number): string {
  const pctValue = item?.suggested_sell_pct ?? fallback;
  if (!pctValue) return "none";
  return `${pctValue}% ${item?.urgency || ""}`.trim();
}

function amountLabel(item: WatchlistItem | undefined, protection?: { token_amount?: number | null; token_amount_raw?: number | null }): string {
  const amount = item?.token_amount ?? protection?.token_amount;
  const raw = item?.token_amount_raw ?? protection?.token_amount_raw;
  if (typeof amount === "number" && Number.isFinite(amount) && amount > 0) return amount.toLocaleString(undefined, { maximumFractionDigits: 6 });
  if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) return `${raw.toLocaleString()} raw`;
  return "missing";
}

function amountDetail(item: WatchlistItem | undefined, protection?: { token_amount_reason?: string | null; wallet_balance_status?: string | null; wallet_balance_accounts?: number | null; token_decimals?: number | null; quote_reason?: string | null }): string {
  const status = item?.wallet_balance_status ?? protection?.wallet_balance_status ?? "not_checked";
  const accounts = item?.wallet_balance_accounts ?? protection?.wallet_balance_accounts;
  const decimals = item?.token_decimals ?? protection?.token_decimals;
  const reason = item?.token_amount_reason ?? protection?.token_amount_reason ?? item?.quote_reason ?? protection?.quote_reason ?? "amount status pending";
  return `Balance: ${status}${accounts != null ? ` | accounts ${accounts}` : ""}${decimals != null ? ` | decimals ${decimals}` : ""} | ${reason}`;
}

type ReadinessRow = {
  label: string;
  status: string;
  detail: string;
  tone: "good" | "warn" | "bad";
};

function buildExitReadiness(item: WatchlistItem | undefined, protection?: ProtectionSummary): ReadinessRow[] {
  const hasAmount = hasUsableAmount(item, protection);
  const isTestAmount = Boolean(item?.test_amount || protection?.test_amount);
  const walletStatus = item?.wallet_balance_status || protection?.wallet_balance_status || "not_checked";
  const quoteStatus = String(item?.quote_status || protection?.quote_status || "not_checked").toLowerCase();
  const autoSellRequested = Boolean(item?.auto_sell || protection?.auto_sell_enabled);
  const liveAllowed = Boolean(item?.live_action_allowed || protection?.live_action_allowed);

  return [
    {
      label: "Position amount",
      status: hasAmount ? (isTestAmount ? "TEST" : "SET") : "MISSING",
      detail: hasAmount
        ? amountReadinessDetail(item, protection)
        : "Add a wallet-derived or manually verified token amount before a real route check can be trusted.",
      tone: hasAmount ? (isTestAmount ? "warn" : "good") : "bad",
    },
    {
      label: "Ownership source",
      status: sourceStatus(walletStatus, isTestAmount),
      detail: sourceDetail(walletStatus, isTestAmount),
      tone: sourceTone(walletStatus, isTestAmount),
    },
    {
      label: "Sell-route quote",
      status: quoteStatusLabel(quoteStatus),
      detail: item?.quote_reason || protection?.quote_reason || "No quote reason recorded yet.",
      tone: quoteTone(quoteStatus),
    },
    {
      label: "Live execution gate",
      status: liveAllowed ? "UNLOCKED" : "LOCKED",
      detail: liveAllowed
        ? "Live action is allowed by local state. Confirm explicit operator intent before any real order path."
        : "Expected state: live sell routes remain locked while the system is still paper-first.",
      tone: liveAllowed ? "bad" : "good",
    },
    {
      label: "Auto-sell state",
      status: autoSellRequested ? "REQUESTED" : "OFF",
      detail: autoSellRequested
        ? "Interest may be stored, but auto-sell must remain blocked until live gates, audit records, and kill switch are complete."
        : "No active auto-sell. Watchdog can advise and prepare simulation exits only.",
      tone: autoSellRequested ? "warn" : "good",
    },
  ];
}

function hasUsableAmount(item: WatchlistItem | undefined, protection?: ProtectionSummary): boolean {
  const amount = item?.token_amount ?? protection?.token_amount;
  const raw = item?.token_amount_raw ?? protection?.token_amount_raw;
  return (
    (typeof amount === "number" && Number.isFinite(amount) && amount > 0) ||
    (typeof raw === "number" && Number.isFinite(raw) && raw > 0)
  );
}

function amountReadinessDetail(item: WatchlistItem | undefined, protection?: ProtectionSummary): string {
  const amount = amountLabel(item, protection);
  const source = item?.token_amount_source || protection?.token_amount_source || "unknown_source";
  const decimals = item?.token_decimals ?? protection?.token_decimals;
  return `${amount} from ${source}${decimals != null ? `, decimals ${decimals}` : ""}.`;
}

function sourceStatus(walletStatus: string, isTestAmount: boolean): string {
  if (isTestAmount) return "SIMULATED";
  if (["wallet_balance", "wallet_found", "found"].includes(walletStatus)) return "WALLET";
  if (walletStatus === "manual_amount") return "MANUAL";
  if (walletStatus === "amount_missing") return "MISSING";
  return walletStatus.toUpperCase();
}

function sourceDetail(walletStatus: string, isTestAmount: boolean): string {
  if (isTestAmount) return "This amount is useful for route testing but must not be treated as an owned wallet balance.";
  if (["wallet_balance", "wallet_found", "found"].includes(walletStatus)) return "Amount came from token account lookup.";
  if (walletStatus === "manual_amount") return "Amount was entered manually and should be verified against the trading wallet.";
  if (walletStatus === "amount_missing") return "No owned or manually supplied amount is available.";
  return "Ownership source is recorded in local watchlist state.";
}

function sourceTone(walletStatus: string, isTestAmount: boolean): "good" | "warn" | "bad" {
  if (isTestAmount || walletStatus === "manual_amount") return "warn";
  if (["wallet_balance", "wallet_found", "found"].includes(walletStatus)) return "good";
  if (walletStatus === "amount_missing") return "bad";
  return "warn";
}

function quoteStatusLabel(quoteStatus: string): string {
  if (["feasible", "quote_passed", "passed"].includes(quoteStatus)) return "FEASIBLE";
  if (["amount_missing", "missing_amount"].includes(quoteStatus)) return "NO AMOUNT";
  if (["blocked", "failed", "quote_failed", "infeasible"].includes(quoteStatus)) return "BLOCKED";
  return quoteStatus.toUpperCase();
}

function quoteTone(quoteStatus: string): "good" | "warn" | "bad" {
  if (["feasible", "quote_passed", "passed"].includes(quoteStatus)) return "good";
  if (["amount_missing", "missing_amount", "not_checked", "pending"].includes(quoteStatus)) return "warn";
  return "bad";
}
