import { formatNumber } from "../format";
import type { PurchasePeriod, PurchaseProduct } from "../types";
const purchasePeriods = [["30d", "30 дней"], ["60d", "60 дней"], ["90d", "90 дней"], ["all", "Всё время"]] as const;

export function PurchasePeriodSelect({ value, onChange }: {
  value: PurchasePeriod;
  onChange: (value: PurchasePeriod) => void;
}) {
  return (
    <select className="input purchase-period" aria-label="Период закупок" value={value}
      onChange={(event) => onChange(event.target.value as PurchasePeriod)}>
      {purchasePeriods.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
  );
}

export function purchaseMoney(value: string | number) {
  return `${formatNumber(value)} ₽`;
}

const trendNames = {
  rapid_growth: "Быстрый рост", rising: "Рост цены", stable: "Стабильная цена",
  falling: "Снижение цены", insufficient: "Мало данных",
};

export function PurchaseTrend({ trend }: {
  trend: PurchaseProduct["price_trend"];
}) {
  if (trend.change_pct === null) return <span className="muted-cell">Мало данных</span>;
  const change = Number(trend.change_pct);
  const label = trendNames[trend.status];
  if (change === 0) return <span className="muted-cell">Без изменений</span>;
  return (
    <span className={`purchase-trend trend-${trend.status}`} title={label}>
      {change > 0 ? "+" : change < 0 ? "−" : ""}{formatNumber(Math.abs(change))}%
    </span>
  );
}
