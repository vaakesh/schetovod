// monday is 0, as the api counts them
export const WEEKDAYS = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
  "Воскресенье",
];

export const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function hourRange(hour: number): string {
  return `${hour}:00–${hour + 1}:00`;
}

// a receipt count is an average, one digit after the comma is enough
const count = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 1,
});

export function formatCount(value: number | null): string {
  return value === null ? "—" : count.format(value);
}

// a forecast speaks of people, nobody plans a shift for half a customer
export function formatPeople(value: number | null): string {
  return value === null ? "—" : count.format(Math.round(value));
}

const rubles = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
});

export function formatRubles(value: string | number | null): string {
  return value === null ? "—" : `${rubles.format(Number(value))} ₽`;
}

// thousands of rubles do not fit the margin of a chart in full
export function formatThousands(value: number): string {
  return value < 1000 ? count.format(value) : `${count.format(value / 1000)}к`;
}

// percent of the plan, a plan of nothing has no share to count
export function deviation(fact: number, plan: number): number | null {
  return plan > 0 ? Math.round(((fact - plan) / plan) * 100) : null;
}

export function formatDeviation(value: number | null): string {
  if (value === null) {
    return "—";
  }
  if (value === 0) {
    return "0%";
  }
  return `${value > 0 ? "+" : "−"}${Math.abs(value)}%`;
}

// the days of the epoch keep the gaps on a time axis, the api date is DD-MM-YYYY
export function dayNumber(value: string): number {
  const [day, month, year] = value.split("-").map(Number);
  return Date.UTC(year!, month! - 1, day!) / 86_400_000;
}

// the day and the month of a day of the epoch, DD.MM
export function formatDayNumber(value: number): string {
  const [, month, day] = new Date(value * 86_400_000).toISOString().slice(0, 10).split("-");
  return `${day}.${month}`;
}
