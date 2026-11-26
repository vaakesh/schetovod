const EMPTY = "—";

const money = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const number = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 3,
});

export function formatMoney(value: string | number | null): string {
  // Intl keeps every kopeck when a large decimal total is passed as a string
  return value === null ? EMPTY : money.format(value as number | `${number}`);
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

function toKopecks(value: string | null): bigint | null {
  const match = /^(\d{1,12})(?:[.,](\d{1,2}))?$/.exec(value ?? "");
  return match ? BigInt(match[1]! + (match[2] ?? "").padEnd(2, "0")) : null;
}

export function revaluationKopecks(
  quantity: string | null,
  oldPrice: string | null,
  newPrice: string | null,
): bigint | null {
  const units = /^(\d{1,9})(?:[.,](\d{1,3}))?$/.exec(quantity ?? "");
  const previous = toKopecks(oldPrice);
  const next = toKopecks(newPrice);
  if (!units || previous === null || next === null) return null;

  const thousandths = BigInt(units[1]! + (units[2] ?? "").padEnd(3, "0"));
  const amount = thousandths * (next - previous);
  // round each product to a kopeck before adding the lines, just as the ledger does
  return (amount + (amount < 0n ? -500n : 500n)) / 1000n;
}

export function formatSignedKopecks(amount: bigint): string {
  const sign = amount < 0n ? "−" : amount > 0n ? "+" : "";
  const absolute = amount < 0n ? -amount : amount;
  const rubles = `${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
  return sign + formatMoney(rubles);
}

export function formatQuantityFromAmount(amount: string, price: string | null): string | null {
  const total = toKopecks(amount);
  const perUnit = toKopecks(price);
  if (total === null || perUnit === null || perUnit === 0n) return null;

  const scaled = total * 1000n;
  const rounded = (scaled + perUnit / 2n) / perUnit;
  if (total > 0n && rounded === 0n) return "< 0,001";
  const whole = number.format(rounded / 1000n);
  const fraction = String(rounded % 1000n).padStart(3, "0").replace(/0+$/, "");
  const value = fraction ? `${whole},${fraction}` : whole;
  return scaled % perUnit === 0n ? value : `≈ ${value}`;
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

const WEEKDAY = new Intl.DateTimeFormat("ru-RU", { weekday: "long" });

// the heading of a day, a date of the current year goes without the year
export function formatDay(value: string): { date: string; weekday: string } {
  const [day = 0, month = 0, year = 0] = value.split("-").map(Number);
  const date = year === new Date().getFullYear() ? value.slice(0, 5) : value;
  return {
    date: date.replaceAll("-", "."),
    // the local midnight of that day, the time zone can not move it to the next one
    weekday: WEEKDAY.format(new Date(year, month - 1, day)),
  };
}
