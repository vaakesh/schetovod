const EMPTY = "—";

const money = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const number = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 3,
});

export function formatMoney(value: string | number | null): string {
  return value === null ? EMPTY : money.format(Number(value));
}

// a ledger amount always shows its direction, a real minus sign instead of a hyphen
export function formatSigned(value: string | number): string {
  const amount = Number(value);
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}${money.format(Math.abs(amount))}`;
}

export function formatNumber(value: string | number | null): string {
  return value === null ? EMPTY : number.format(Number(value));
}

export function formatText(value: string | number | null): string {
  return value === null || value === "" ? EMPTY : String(value);
}

// the api date is DD-MM-YYYY, people read DD.MM.YYYY
export function formatDate(value: string | null): string {
  return value === null ? EMPTY : value.replaceAll("-", ".");
}
