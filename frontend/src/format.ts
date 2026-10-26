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

const dateTime = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

// a moment from the api in the browser time zone
export function formatDateTime(value: string): string {
  return dateTime.format(new Date(value));
}

// the russian form for a count: 1 позиция, 2 позиции, 5 позиций
export function plural(count: number, one: string, few: string, many: string): string {
  const tens = count % 100;
  const units = count % 10;
  if (tens >= 11 && tens <= 14) {
    return many;
  }
  if (units === 1) {
    return one;
  }
  return units >= 2 && units <= 4 ? few : many;
}

// the api date is DD-MM-YYYY, people read DD.MM.YYYY
export function formatDate(value: string | null): string {
  return value === null ? EMPTY : value.replaceAll("-", ".");
}
