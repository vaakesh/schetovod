import { useEffect, useMemo, useState } from "react";

import { getPurchaseReport } from "../api";
import Icon from "../components/icons";
import PageHead from "../components/PageHead";
import { purchaseMoney, PurchasePeriodSelect, PurchaseTrend } from "../components/PurchaseControls";
import PurchaseHistoryDialog from "../components/PurchaseHistoryDialog";
import PurchaseMenu from "../components/PurchaseMenu";
import PurchaseOverview from "../components/PurchaseOverview";
import { formatDate, formatNumber, plural } from "../format";
import { message } from "../message";
import { days, scheduleDeviation, scheduleLabel, usualCadence } from "../purchaseSchedule";
import { routeHash } from "../router";
import type { PurchasePeriod, PurchaseProduct, PurchaseReport } from "../types";
import "../purchases.css";

const sortFields = {
  schedule: ["Срок поставки", "С задержкой", "С запасом времени"],
  spend: ["Расходы", "Большие расходы", "Малые расходы"],
  deliveries: ["Число поставок", "Больше поставок", "Меньше поставок"],
  price: ["Изменение цены", "Рост цены", "Снижение цены"],
  days_since: ["Последняя поставка", "Давние поставки", "Недавние поставки"],
  usual_interval_days: ["Обычный интервал", "Длинный интервал", "Короткий интервал"],
} as const;
type SortField = keyof typeof sortFields;
type Order = { field: SortField; descending: boolean };
const sortGroups = (Object.keys(sortFields) as SortField[]).map((field) => ({
  label: sortFields[field][0],
  options: [[`${field}-1`, sortFields[field][1]], [`${field}-0`, sortFields[field][2]]] as const,
}));

function sortValue(item: PurchaseProduct, field: SortField) {
  switch (field) {
    case "schedule": return scheduleDeviation(item);
    case "price": return item.price_trend.change_pct === null ? null : Number(item.price_trend.change_pct);
    case "usual_interval_days": return item.usual_interval_days === null ? null : Number(item.usual_interval_days);
    default: return Number(item[field]);
  }
}

function TimingValue({ item, field }: { item: PurchaseProduct; field: SortField }) {
  if (field === "days_since") return <>{days(item.days_since)} без поставок<small>{formatDate(item.last_on)}</small></>;
  if (field === "usual_interval_days") return <>{item.usual_interval_days === null ? "Интервал пока неизвестен" : usualCadence(item)}</>;
  return <><span className={item.overdue ? "purchase-late" : undefined}>{scheduleLabel(item)}</span>
    <small>{item.usual_interval_days === null ? "Интервал пока неизвестен" : usualCadence(item)}</small></>;
}

export default function PurchasesPage() {
  const [period, setPeriod] = useState<PurchasePeriod>("30d");
  const [order, setOrder] = useState<Order>({ field: "schedule", descending: true });
  const [search, setSearch] = useState("");
  const [supplier, setSupplier] = useState<Pick<PurchaseProduct, "supplier_id" | "supplier_name"> | null>(null);
  const [activeOnly, setActiveOnly] = useState(false);
  const [result, setResult] = useState<PurchaseReport | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [product, setProduct] = useState<PurchaseProduct | null>(null);
  const report = result?.period === period ? result : null;

  useEffect(() => {
    let current = true;
    setError("");
    setResult(null);
    getPurchaseReport(period, "last_delivery")
      .then((next) => current && setResult(next))
      .catch((reason) => current && setError(message(reason)));
    return () => { current = false; };
  }, [period, attempt]);

  const suppliers = new Map<number, string>();
  if (supplier) suppliers.set(supplier.supplier_id, supplier.supplier_name);
  for (const item of report?.items ?? []) suppliers.set(item.supplier_id, item.supplier_name);
  const supplierOptions = [...suppliers].sort((a, b) => a[1].localeCompare(b[1], "ru"))
    .map(([id, name]) => [String(id), name] as const);
  const query = search.trim().toLocaleLowerCase("ru");
  const items = useMemo(() => report?.items.filter((item) =>
    (!activeOnly || item.deliveries > 0) && (!supplier || item.supplier_id === supplier.supplier_id)
      && item.name.toLocaleLowerCase("ru").includes(query),
  ).sort((a, b) => {
    const left = sortValue(a, order.field);
    const right = sortValue(b, order.field);
    const comparison = left === null || right === null ? Number(left === null) - Number(right === null)
      : order.descending ? right - left : left - right;
    return comparison || a.name.localeCompare(b.name, "ru") || a.product_id - b.product_id;
  }), [report, supplier, query, order, activeOnly]);
  const filterCount = Number(Boolean(supplier)) + Number(activeOnly);
  const expenseFirst = order.field === "spend" || order.field === "deliveries";
  const timingField = ["usual_interval_days", "days_since"].includes(order.field) ? order.field : "schedule";

  function resetFilters() {
    setSearch("");
    setSupplier(null);
    setActiveOnly(false);
  }

  function sortHeader(field: SortField, label: string) {
    const active = order.field === field;
    return <th scope="col" className={field === timingField ? undefined : "num"}
      aria-sort={active ? (order.descending ? "descending" : "ascending") : undefined}>
      <button className={active ? "sort-button active" : "sort-button"}
        onClick={() => setOrder({ field, descending: !active || !order.descending })}>
        {label}{active && <span aria-hidden="true">{order.descending ? " ↓" : " ↑"}</span>}
      </button>
    </th>;
  }

  return (
    <main className="page purchases">
      <PageHead title="Закупки" meta={report && `Данные на ${formatDate(report.as_of)}`}>
        <PurchasePeriodSelect value={period} onChange={setPeriod} />
      </PageHead>
      <PurchaseOverview key={`${period}-${supplier?.supplier_id ?? "all"}`}
        period={period} supplierId={supplier?.supplier_id ?? null} supplierName={supplier?.supplier_name} />
      <section className="sheet purchase-sheet" aria-labelledby="purchase-products">
        <div className="purchase-tools">
          <div className="purchase-list-head">
            <h2 id="purchase-products">Товары {items && <span>{formatNumber(items.length)}</span>}</h2>
            <div className="purchase-sort">
              <PurchaseMenu label="Сортировка товаров" icon="sort" value={`${order.field}-${Number(order.descending)}`}
                groups={sortGroups} title={`Сначала ${sortFields[order.field][order.descending ? 1 : 2].toLocaleLowerCase("ru")}`}
                onChange={(value) => {
                  const [field, direction] = value.split("-");
                  setOrder({ field: field as SortField, descending: direction === "1" });
                }} />
            </div>
          </div>
          <div className="purchase-search-row">
            <label className="purchase-search"><Icon name="search" size={17} />
              <input type="search" className="input" aria-label="Поиск по товарам" placeholder="Найти товар"
                value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
            <div className="purchase-supplier" data-active={Boolean(supplier)}>
              <PurchaseMenu label="Поставщик" icon="supplier" value={String(supplier?.supplier_id ?? "")}
                groups={[{ options: [["", "Все поставщики"], ...supplierOptions] }]}
                onChange={(value) => {
                  const id = Number(value);
                  setSupplier(id ? { supplier_id: id, supplier_name: suppliers.get(id)! } : null);
                }} />
            </div>
            <label className="purchase-active-only"><input type="checkbox" checked={activeOnly}
              onChange={(event) => setActiveOnly(event.target.checked)} /> Только с поставками за период</label>
          </div>
        </div>
        {error ? <div className="list-empty" role="alert">{error}
          <button className="button button-ghost" onClick={() => setAttempt(attempt + 1)}>Повторить</button>
        </div> : !items ? <p className="list-empty" role="status">Загружаем закупки…</p>
        : !items.length ? <div className="list-empty">
          <p>{activeOnly && !query ? "За выбранный период поставок нет" : query || filterCount
            ? "По этим условиям товаров нет" : "Товары появятся после проведения первой накладной"}</p>
          {activeOnly && !query && period !== "all" &&
            <button className="button button-ghost" onClick={() => setPeriod("all")}>Показать всё время</button>}
          {query || filterCount ? <button className="button button-ghost" onClick={resetFilters}>Сбросить фильтры</button>
            : <a className="op-link" href={routeHash({ page: "invoices" })}>К накладным</a>}
        </div> : (
          <table className="list purchase-list" data-primary={expenseFirst ? "expense" : order.field === "price" ? "price" : "timing"}>
            <thead><tr><th scope="col">Товар</th>{sortHeader(timingField, sortFields[timingField][0])}
              {sortHeader(order.field === "deliveries" ? "deliveries" : "spend", order.field === "deliveries" ? "Поставки" : "Расходы")}
              {sortHeader("price", "Изменение цены")}<th scope="col" aria-label="История закупок" /></tr></thead>
            <tbody>{items.map((item) => {
              const deliveries = `${item.deliveries} ${plural(item.deliveries, "поставка", "поставки", "поставок")}`;
              const money = purchaseMoney(item.spend);
              return <tr key={item.product_id} className="list-row clickable" onClick={() => setProduct(item)}>
                <td className="purchase-name"><button type="button" className="purchase-open"
                  onClick={(event) => { event.stopPropagation(); setProduct(item); }}>{item.name}</button>
                  <small>{item.supplier_name}</small></td>
                <td className="purchase-timing"><TimingValue item={item} field={timingField} /></td>
                <td className="num purchase-expense">{order.field === "deliveries" ? deliveries : money}
                  <small>{order.field === "deliveries" ? money : deliveries}</small></td>
                <td className="num purchase-price" data-changed={Number(item.price_trend.change_pct) !== 0}>
                  <span className="purchase-mobile-label">{item.price_trend.change_pct === null ? "Изменение цены · " : "Цена "}</span>{item.deliveries === 0
                    ? <span className="muted-cell">Нет поставок за период</span> : <PurchaseTrend trend={item.price_trend} />}</td>
                <td className="purchase-arrow" aria-hidden="true"><Icon name="chevronRight" size={16} /></td>
              </tr>;
            })}</tbody>
          </table>
        )}
      </section>
      {product && <PurchaseHistoryDialog key={product.product_id} product={product} initialPeriod={period}
        onClose={() => setProduct(null)} />}
    </main>
  );
}
