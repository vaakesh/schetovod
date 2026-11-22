import { useEffect, useState } from "react";

import { getPurchaseHistory } from "../api";
import { formatDate, formatNumber } from "../format";
import { message } from "../message";
import { scheduleDeviation, usualCadence } from "../purchaseSchedule";
import { routeHash } from "../router";
import type { PurchaseHistory, PurchaseLine, PurchasePeriod, PurchaseProduct } from "../types";
import Icon from "./icons";
import Modal from "./Modal";
import { PurchasePeriodSelect, PurchaseTrend, purchaseMoney } from "./PurchaseControls";
import PurchaseMenu from "./PurchaseMenu";
import PurchasePriceChart from "./PurchasePriceChart";

function invoiceLabel(line: PurchaseLine) {
  return line.invoice_number ? `№ ${line.invoice_number}` : `#${line.invoice_id}`;
}

function HistoryLines({ history }: { history: PurchaseHistory }) {
  const units = [...new Set(history.lines.map((line) => line.unit))];
  const [unit, setUnit] = useState(history.lines.at(-1)?.unit ?? null);
  const lines = history.lines.filter((line) => line.unit === unit);
  const [picked, setPicked] = useState<number | null>(null);
  const selected = picked ?? lines.length - 1;
  const current = lines[selected]!;
  const quantity = lines.reduce((sum, line) => sum + Number(line.quantity), 0);
  const cost = lines.reduce((sum, line) => sum + Number(line.cost_price_total), 0);
  return <>
    {units.length > 1 && <div className="purchase-unit">Единица измерения
      <PurchaseMenu label="Единица измерения" value={unit ?? ""}
        groups={[{ options: units.map((value) => [value ?? "", value || "Не указана"] as const) }]}
        onChange={(value) => { setUnit(value || null); setPicked(null); }} />
    </div>}
    <dl className="purchase-summary">
      <div><dt>Потрачено</dt><dd>{purchaseMoney(history.product.spend)}</dd></div>
      <div><dt>Поставок</dt><dd>{history.product.deliveries}</dd></div>
      <div><dt>Средняя цена{unit && `, ₽/${unit}`}</dt><dd>{unit && quantity > 0 ? formatNumber((cost / quantity).toFixed(2)) : "—"}</dd></div>
      <div><dt>Изменение цены</dt><dd><PurchaseTrend trend={history.product.price_trend} /></dd></div>
    </dl>
    {unit && <PurchasePriceChart lines={lines} selected={selected} onSelect={setPicked} />}
    <div className="purchase-selection">
      <div className="purchase-point-details" aria-live="polite" aria-atomic="true">
        <strong>{formatDate(current.occurred_on)}</strong>
        <span>{formatNumber(current.quantity)} {unit} по {purchaseMoney(current.cost_price)}{unit && `/${unit}`}</span>
        <a className="op-link" href={routeHash({ page: "posted", id: current.invoice_id })}>Накладная {invoiceLabel(current)}</a>
      </div>
      {lines.length > 1 && <div className="purchase-point-nav" role="group" aria-label="Переключение поставок">
        <button type="button" className="button button-ghost" aria-label="Предыдущая поставка"
          disabled={selected === 0} onClick={() => setPicked(selected - 1)}><Icon name="chevronLeft" size={16} /></button>
        <button type="button" className="button button-ghost" aria-label="Следующая поставка"
          disabled={selected === lines.length - 1} onClick={() => setPicked(selected + 1)}><Icon name="chevronRight" size={16} /></button>
      </div>}
    </div>
    <details className="purchase-invoices"><summary>Все поставки за период</summary>
    <div className="table-wrap purchase-lines-wrap"><table className="list purchase-lines">
      <thead><tr><th>Дата</th><th>Накладная</th><th className="num">Кол-во</th><th className="num">Закупка</th><th className="num">Розница</th></tr></thead>
      <tbody>{lines.map((line, i) => <tr key={`${line.invoice_id}-${line.line_no}`}
        className={`list-row${selected === i ? " purchase-picked" : ""}`} onClick={() => setPicked(i)}>
        <td><button className="purchase-line-date" aria-pressed={selected === i} onClick={() => setPicked(i)}>
          {formatDate(line.occurred_on)}</button></td>
        <td className="purchase-invoice-num"><a className="op-link" href={routeHash({ page: "posted", id: line.invoice_id })}>
          {invoiceLabel(line)}</a></td>
        <td className="num"><span className="purchase-mobile-label">Кол-во </span>{formatNumber(line.quantity)} {unit}</td>
        <td className="num"><span className="purchase-mobile-label">Закупка </span>{purchaseMoney(line.cost_price)}</td>
        <td className="num"><span className="purchase-mobile-label">Розница </span>{purchaseMoney(line.retail_price)}</td>
      </tr>).reverse()}</tbody>
    </table></div></details>
  </>;
}

export default function PurchaseHistoryDialog({ product, initialPeriod, onClose }: {
  product: PurchaseProduct; initialPeriod: PurchasePeriod; onClose: () => void;
}) {
  const [period, setPeriod] = useState(initialPeriod);
  const [history, setHistory] = useState<PurchaseHistory | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  const deviation = scheduleDeviation(product);
  useEffect(() => {
    let current = true;
    setError("");
    setHistory(null);
    getPurchaseHistory(product.product_id, period)
      .then((data) => current && setHistory(data))
      .catch((reason) => current && setError(message(reason)));
    return () => { current = false; };
  }, [product.product_id, period, attempt]);
  return <Modal className="purchase-dialog" onClose={onClose} label="История закупок">
    <div className="purchase-dialog-body">
      <header className="purchase-dialog-head"><div>
        <h2 className="modal-title">{product.name}</h2><small>{product.supplier_name}</small></div>
        <button className="button button-ghost" aria-label="Закрыть историю" onClick={onClose}><Icon name="close" size={18} /></button>
      </header>
      <div className="purchase-history-tools"><div className="purchase-history-cadence">
        <span>Последняя поставка {formatDate(product.last_on)}</span>
        <span>{usualCadence(product)}{deviation !== null && deviation !== 0 &&
          ` · прошло на ${formatNumber(Math.abs(deviation))}% ${deviation > 0 ? "больше" : "меньше"} времени`}</span>
      </div><PurchasePeriodSelect value={period} onChange={setPeriod} /></div>
      {error ? <div className="list-empty" role="alert">{error}
        <button className="button button-ghost" onClick={() => setAttempt(attempt + 1)}>Повторить</button></div>
      : !history || history.period !== period ? <p className="list-empty" role="status">Загружаем поставки…</p>
      : history.lines.length ? <HistoryLines key={period} history={history} />
      : <div className="list-empty"><p>За выбранный период поставок нет</p>
        {period !== "all" && <button className="button button-ghost" onClick={() => setPeriod("all")}>Показать всё время</button>}
      </div>}
    </div>
  </Modal>;
}
