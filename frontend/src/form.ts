import type { DraftForm, FormLine } from "./types";

export type UpdateForm = (update: (form: DraftForm) => DraftForm) => void;

// the api takes decimals as strings with a dot, an empty field is no value
export function toDecimal(input: string): string | null {
  const value = input.trim().replace(",", ".");
  return value === "" ? null : value;
}

// pieces or kilograms with grams, the api rejects anything else
export const QUANTITY = /^\d+(\.\d{1,3})?$/;

// rubles with at most two decimals, the api rejects anything else
export const AMOUNT = /^\d+(\.\d{1,2})?$/;

// the database pads decimals, a form field reads better without the trailing zeros
export function trimDecimal(value: string | null): string | null {
  if (value === null || !value.includes(".")) {
    return value;
  }
  return value.replace(/\.?0+$/, "");
}

export function toText(input: string): string | null {
  return input.trim() === "" ? null : input;
}

// whole rubles only, anything else is dropped while typing
export function toRubles(input: string): number | null {
  const digits = input.replace(/\D/g, "");
  return digits === "" ? null : Number(digits);
}

// the api date is DD-MM-YYYY, a date input works with YYYY-MM-DD
export function toInputDate(value: string | null): string {
  const match = value?.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : "";
}

export function fromInputDate(value: string): string | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : null;
}

// a moment in the browser time zone, as a date input wants it
export function inputDate(moment: Date): string {
  const month = String(moment.getMonth() + 1).padStart(2, "0");
  const day = String(moment.getDate()).padStart(2, "0");
  return `${moment.getFullYear()}-${month}-${day}`;
}

export function todayInput(): string {
  return inputDate(new Date());
}

export function shiftInput(value: string, days: number): string {
  const [year, month, day] = value.split("-").map(Number);
  return inputDate(new Date(year!, month! - 1, day! + days));
}

export function emptyLine(lineNo: number): FormLine {
  return {
    line_no: lineNo,
    name: null,
    quantity: null,
    unit: null,
    vat_percent: null,
    cost_price_total: null,
    product_id: null,
    retail_price: null,
    revalue_quantity: null,
  };
}

export function updateLine(update: UpdateForm, index: number, changes: Partial<FormLine>) {
  update((form) => ({
    ...form,
    lines: form.lines.map((line, position) => (position === index ? { ...line, ...changes } : line)),
  }));
}
