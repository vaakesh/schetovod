import { useEffect, useState } from "react";

import { addRevaluation, getBalance, searchProducts, searchSuppliers } from "../api";
import { formatNumber, formatSignedKopecks, revaluationKopecks } from "../format";
import { fromInputDate, toDecimal, toInputDate, todayInput, toText } from "../form";
import { message } from "../message";
import type { ProductSummary, SupplierSummary } from "../types";
import Modal from "./Modal";
import RetailPriceInput from "./RetailPriceInput";

interface Props {
  onClose: () => void;
  onPosted: () => void;
}

interface Line {
  product: ProductSummary;
  quantity: string | null;
  price: string | null;
}

const SEARCH_DELAY_MS = 250;
// the api pages are at most this long, a shop has fewer suppliers
const SUPPLIERS_LIMIT = 200;

export default function RevaluationDialog({ onClose, onPosted }: Props) {
  const [date, setDate] = useState(todayInput);
  const [closedOn, setClosedOn] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [suppliers, setSuppliers] = useState<SupplierSummary[]>([]);
  const [supplierId, setSupplierId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [found, setFound] = useState<ProductSummary[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    searchSuppliers("", SUPPLIERS_LIMIT)
      .then((list) => {
        if (current) {
          setSuppliers(list);
          setSupplierId(list[0]?.id ?? null);
        }
      })
      .catch((reason) => current && setError(message(reason)));
    // the day the period is closed on, nothing may be dated before it
    getBalance(null)
      .then((balance) => current && setClosedOn(balance.closed_on))
      .catch(() => current && setClosedOn(null));
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (supplierId === null) {
      setFound([]);
      return;
    }
    let current = true;
    const timer = window.setTimeout(() => {
      searchProducts(supplierId, search)
        .then((products) => current && setFound(products))
        .catch((reason) => current && setError(message(reason)));
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [supplierId, search]);

  const chosen = new Set(lines.map((line) => line.product.id));
  const amounts = lines.map((line) =>
    revaluationKopecks(line.quantity, line.product.retail_price, line.price),
  );
  const valid =
    lines.length > 0 &&
    amounts.every((amount) => amount !== null) &&
    lines.every((line) => Number(line.price) > 0 && Number(line.price) !== Number(line.product.retail_price));
  const total = amounts.reduce<bigint>((sum, amount) => sum + (amount ?? 0n), 0n);

  function change(index: number, changes: Partial<Line>) {
    setLines((current) =>
      current.map((line, position) => (position === index ? { ...line, ...changes } : line)),
    );
  }

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addRevaluation({
        occurred_on: fromInputDate(date) ?? "",
        comment: toText(comment),
        lines: lines.map((line) => ({
          product_id: line.product.id,
          quantity: line.quantity ?? "",
          new_price: line.price ?? "",
        })),
      });
      onPosted();
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="modal-form modal-wide">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">Переоценка</h2>
          <p className="modal-text">
            Новая цена для товара, который уже на полке. Наценка товара не меняется.
          </p>
          <div className="fields">
            <div className="field-row">
              <label className="field">
                <span className="field-label">Дата</span>
                <input
                  className="input"
                  type="date"
                  required
                  value={date}
                  max={todayInput()}
                  min={toInputDate(closedOn) || undefined}
                  onChange={(event) => setDate(event.target.value)}
                />
              </label>
              <label className="field field-grow">
                <span className="field-label">Комментарий</span>
                <input
                  className="input"
                  placeholder="Например, акция"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                />
              </label>
            </div>

            <div className="field-row">
              <label className="field">
                <span className="field-label">Продавец</span>
                <select
                  className="input"
                  value={supplierId ?? ""}
                  onChange={(event) => setSupplierId(Number(event.target.value) || null)}
                >
                  {suppliers.map((supplier) => (
                    <option key={supplier.id} value={supplier.id}>
                      {supplier.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field field-grow">
                <span className="field-label">Товар</span>
                <input
                  className="input"
                  type="search"
                  placeholder="Часть названия"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
            </div>
            <ul className="reval-found">
              {found
                .filter((product) => !chosen.has(product.id))
                .map((product) => (
                  <li key={product.id}>
                    <button
                      type="button"
                      className="reval-found-item"
                      onClick={() =>
                        setLines((current) => [...current, { product, quantity: null, price: null }])
                      }
                    >
                      <span className="reval-name">{product.name}</span>
                      <span className="reval-price">{formatNumber(product.retail_price)} ₽</span>
                    </button>
                  </li>
                ))}
              {supplierId !== null && found.length === 0 && (
                <li className="reval-empty">Ничего не нашлось</li>
              )}
            </ul>

            {lines.length > 0 && (
              <table className="reval-lines">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th className="num">Было</th>
                    <th className="num">На полке</th>
                    <th className="num">Стало, ₽</th>
                    <th className="num">Сумма</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => {
                    const amount = amounts[index] ?? null;
                    return (
                      <tr key={line.product.id}>
                        <td className="reval-name">{line.product.name}</td>
                        <td className="num muted-cell">{formatNumber(line.product.retail_price)}</td>
                        <td>
                          <input
                            className="cell cell-num cell-short"
                            inputMode="decimal"
                            placeholder={line.product.unit ?? "0"}
                            value={line.quantity ?? ""}
                            onChange={(event) =>
                              change(index, { quantity: toDecimal(event.target.value) })
                            }
                          />
                        </td>
                        <td>
                          <RetailPriceInput
                            className="cell cell-num cell-short"
                            placeholder="₽"
                            value={line.price}
                            onChange={(price) => change(index, { price })}
                          />
                        </td>
                        <td className="num nowrap">{amount === null ? "—" : formatSignedKopecks(amount)}</td>
                        <td>
                          <button
                            type="button"
                            className="row-delete"
                            title="Убрать"
                            onClick={() =>
                              setLines((current) => current.filter((_, position) => position !== index))
                            }
                          >
                            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeWidth="1.4" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {lines.length > 0 && (
              <dl className="stocktake-preview">
                <div>
                  <dt>Остаток изменится на</dt>
                  <dd>{valid ? `${formatSignedKopecks(total)} ₽` : "—"}</dd>
                </div>
                <div>
                  <dt>Товаров</dt>
                  <dd>{lines.length}</dd>
                </div>
              </dl>
            )}
          </div>
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={!valid || busy}>
            Записать
          </button>
        </div>
      </form>
    </Modal>
  );
}
