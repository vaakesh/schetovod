import { formatMoney } from "./format";
import type { PriceTag, PriceTagOrigin, PriceTagPrintRow, PriceTagUnit } from "./types";

// the four sizes the shop cuts, width by height in mm
export const SIZES = [
  { key: "40x50", label: "4×5", width: 40, height: 50 },
  { key: "50x80", label: "5×8", width: 50, height: 80 },
  { key: "60x70", label: "6×7", width: 60, height: 70 },
  { key: "70x100", label: "7×10", width: 70, height: 100 },
] as const;

export type SizeKey = (typeof SIZES)[number]["key"];

export const UNIT_LABELS: Record<PriceTagUnit, string> = {
  piece: "ШТ.",
  weight: "ВЕС",
};

export const ORIGIN_LABELS: Record<PriceTagOrigin, string> = {
  maker: "Производитель",
  country: "Страна",
};

export const MAX_COPIES = 100;

// one line of the form, the inputs keep what was typed
export interface FormRow {
  key: number;
  size: SizeKey | "";
  unit: PriceTagUnit;
  pack: string;
  name: string;
  subtitle: string;
  rub: string;
  kop: string;
  origin: PriceTagOrigin;
  originName: string;
  quantity: string;
}

export type RowField = "size" | "name" | "rub" | "kop" | "originName" | "quantity";

let lastKey = 0;

function nextKey(): number {
  lastKey += 1;
  return lastKey;
}

export function emptyRow(): FormRow {
  return {
    key: nextKey(),
    size: "",
    unit: "piece",
    pack: "",
    name: "",
    subtitle: "",
    rub: "",
    kop: "",
    // most tags of the shop show the country
    origin: "country",
    originName: "",
    quantity: "1",
  };
}

export function isEmptyRow(row: FormRow): boolean {
  return [row.size, row.pack, row.name, row.subtitle, row.rub, row.kop, row.originName].every(
    (value) => value.trim() === "",
  );
}

function sizeKey(width: number, height: number): SizeKey | "" {
  return SIZES.find((size) => size.width === width && size.height === height)?.key ?? "";
}

export function sizeLabel(width: number, height: number): string {
  return SIZES.find((size) => size.width === width && size.height === height)?.label ?? "";
}

// a picked tag fills every printed field, the number of copies stays
export function fillRow(row: FormRow, tag: PriceTag): FormRow {
  const [rub = "", kop = ""] = tag.price === null ? [] : tag.price.split(".");
  return {
    ...row,
    size: sizeKey(tag.width_mm, tag.height_mm),
    unit: tag.unit,
    pack: tag.pack ?? "",
    name: tag.name,
    subtitle: tag.subtitle ?? "",
    rub,
    kop,
    origin: tag.origin,
    originName: tag.origin_name,
  };
}

// the fields that block the print, the rows left empty are skipped by the caller
export function rowProblems(row: FormRow): Set<RowField> {
  const problems = new Set<RowField>();
  if (row.size === "") {
    problems.add("size");
  }
  if (row.name.trim() === "") {
    problems.add("name");
  }
  if (!/^\d+$/.test(row.rub.trim())) {
    problems.add("rub");
  }
  if (row.kop.trim() !== "" && !/^\d{1,2}$/.test(row.kop.trim())) {
    problems.add("kop");
  }
  if (row.originName.trim() === "") {
    problems.add("originName");
  }
  const quantity = Number(row.quantity);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > MAX_COPIES) {
    problems.add("quantity");
  }
  return problems;
}

export function printRow(row: FormRow): PriceTagPrintRow {
  const size = SIZES.find((option) => option.key === row.size)!;
  return {
    width_mm: size.width,
    height_mm: size.height,
    unit: row.unit,
    pack: row.pack.trim() || null,
    name: row.name.trim(),
    subtitle: row.subtitle.trim() || null,
    price: `${Number(row.rub.trim())}.${(row.kop.trim() || "0").padStart(2, "0")}`,
    origin: row.origin,
    origin_name: row.originName.trim(),
    quantity: Number(row.quantity),
  };
}

// what tells two similar tags apart in the list of suggestions
export function tagDetails(tag: PriceTag): string {
  return [
    sizeLabel(tag.width_mm, tag.height_mm),
    [UNIT_LABELS[tag.unit], tag.pack].filter(Boolean).join(" "),
    tag.price === null ? "без цены" : `${formatMoney(tag.price)} ₽`,
    tag.origin_name,
  ].join(" · ");
}

const STORAGE_KEY = "price-tags-form";

// the form outlives a switch to another page and a reload
export function loadRows(): FormRow[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    if (Array.isArray(saved) && saved.length > 0) {
      return (saved as Omit<FormRow, "key">[]).map((row) => ({ ...emptyRow(), ...row, key: nextKey() }));
    }
  } catch {
    // a broken record starts a clean form
  }
  return [emptyRow()];
}

export function saveRows(rows: FormRow[]) {
  const kept = rows.filter((row) => !isEmptyRow(row));
  if (kept.length === 0) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(kept.map(({ key: _key, ...row }) => row)),
  );
}
