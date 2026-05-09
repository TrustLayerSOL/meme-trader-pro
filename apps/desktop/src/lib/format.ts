export function money(value: number | null | undefined): string {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "-";
  if (Math.abs(number) >= 1_000_000) return `$${(number / 1_000_000).toFixed(2)}M`;
  if (Math.abs(number) >= 1_000) return `$${(number / 1_000).toFixed(1)}K`;
  return `$${number.toFixed(2)}`;
}

export function price(value: number | null | undefined): string {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "-";
  if (Math.abs(number) < 0.0001) return `$${number.toExponential(2)}`;
  if (Math.abs(number) < 0.01) return `$${number.toFixed(6)}`;
  return `$${number.toFixed(4)}`;
}

export function pct(value: number | null | undefined): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(2)}%`;
}

export function shortMint(mint: string | null | undefined): string {
  if (!mint) return "-";
  return mint.length > 14 ? `${mint.slice(0, 8)}...${mint.slice(-4)}` : mint;
}
