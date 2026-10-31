import { fromInputDate, inputDate } from "./form";

export interface ApiPeriod {
  from: string;
  to: string;
}

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

// the days of the epoch keep the gaps on a time axis, the api date is DD-MM-YYYY
export function dayNumber(value: string): number {
  const [day, month, year] = value.split("-").map(Number);
  return Date.UTC(year!, month! - 1, day!) / 86_400_000;
}

// the page of a year of receipts does not fit one request, a month at a time does
export function monthsOf(dateFrom: string, dateTo: string): ApiPeriod[] {
  const periods: ApiPeriod[] = [];
  let start = dateFrom;
  while (start <= dateTo) {
    const [year, month] = start.split("-").map(Number);
    const monthEnd = inputDate(new Date(year!, month!, 0));
    const end = monthEnd < dateTo ? monthEnd : dateTo;
    periods.push({ from: fromInputDate(start)!, to: fromInputDate(end)! });
    start = inputDate(new Date(year!, month!, 1));
  }
  return periods;
}
