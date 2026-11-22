import { formatNumber, plural } from "./format";
import type { PurchaseProduct } from "./types";

export function days(value: number) {
  return `${formatNumber(value)} ${Number.isInteger(value) ? plural(value, "день", "дня", "дней") : "дня"}`;
}

export function scheduleDeviation(item: PurchaseProduct) {
  if (item.usual_interval_days === null) return null;
  const interval = Number(item.usual_interval_days);
  return Math.round((item.days_since - interval) * 1000 / interval) / 10;
}

export function usualCadence(item: PurchaseProduct) {
  if (item.usual_interval_days === null) return "Для графика нужны поставки в четыре разных дня";
  const interval = Number(item.usual_interval_days);
  return interval === 1 ? "Обычно каждый день" : `Обычно раз в ${days(interval)}`;
}

export function scheduleLabel(item: PurchaseProduct) {
  if (item.usual_interval_days === null) {
    const count = item.lifetime_deliveries;
    return `${count} ${plural(count, "поставка", "поставки", "поставок")} за всё время`;
  }
  const difference = item.days_since - Number(item.usual_interval_days);
  if (difference === 0) return "Обычно привозят сегодня";
  return difference > 0 ? `На ${days(difference)} позже обычного` : `Ожидается через ${days(-difference)}`;
}
