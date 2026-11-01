import { todayInput } from "./form";
import { formatRubles } from "./traffic";
import type { ExpenseBasis, ExpenseForm } from "./types";

export const BASES: { value: ExpenseBasis; label: string; unit: string }[] = [
  { value: "month", label: "В месяц", unit: "₽" },
  { value: "year", label: "В год", unit: "₽" },
  { value: "work_day", label: "За рабочий день", unit: "₽" },
  { value: "revenue_percent", label: "Процент от выручки", unit: "%" },
  { value: "card_percent", label: "Процент от безнала", unit: "%" },
];

export function isPercent(basis: ExpenseBasis): boolean {
  return basis === "revenue_percent" || basis === "card_percent";
}

export function expenseRate({ basis, amount }: Pick<ExpenseForm, "basis" | "amount">): string {
  const percent = Number(amount).toLocaleString("ru-RU");
  switch (basis) {
    case "month":
      return `${formatRubles(amount)} в месяц`;
    case "year":
      return `${formatRubles(amount)} в год`;
    case "work_day":
      return `${formatRubles(amount)} за рабочий день`;
    case "revenue_percent":
      return `${percent}% от выручки`;
    case "card_percent":
      return `${percent}% от безнала`;
  }
}

const monthName = new Intl.DateTimeFormat("ru-RU", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

// the api date of the first day of a month, DD-MM-YYYY
function apiMonth(moment: Date): string {
  const month = String(moment.getUTCMonth() + 1).padStart(2, "0");
  return `01-${month}-${moment.getUTCFullYear()}`;
}

function parseMonth(value: string): Date {
  const [, month, year] = value.split("-").map(Number);
  return new Date(Date.UTC(year!, month! - 1, 1));
}

// октябрь 2026, without the abbreviation of the year
export function monthLabel(value: string): string {
  return monthName.format(parseMonth(value)).replace(/\s*г\.$/, "");
}

export function currentMonth(): string {
  const [year, month] = todayInput().split("-");
  return `01-${month}-${year}`;
}

export function shiftMonth(value: string, months: number): string {
  const moment = parseMonth(value);
  moment.setUTCMonth(moment.getUTCMonth() + months);
  return apiMonth(moment);
}

// the months from the first to the last, both included
export function monthRange(first: string, last: string): string[] {
  const months: string[] = [];
  const end = parseMonth(last).getTime();
  for (let month = first; parseMonth(month).getTime() <= end; month = shiftMonth(month, 1)) {
    months.push(month);
  }
  return months;
}
