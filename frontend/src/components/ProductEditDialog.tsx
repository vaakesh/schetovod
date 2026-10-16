import { useEffect, useState } from "react";

import { editProduct, getBalance } from "../api";
import { formatNumber, formatSigned } from "../format";
import { fromInputDate, toDecimal, toInputDate, todayInput, toRubles, toText } from "../form";
import { message } from "../message";
import type { CatalogProduct, LedgerPosted } from "../types";
import Modal from "./Modal";

interface Props {
  product: CatalogProduct;
  onClose: () => void;
  // null when the price changed without a revaluation
  onSaved: (posted: LedgerPosted | null) => void;
}

// pieces or kilograms with grams, the api rejects anything else
const QUANTITY = /^\d+(\.\d{1,3})?$/;

export default function ProductEditDialog({ product, onClose, onSaved }: Props) {
  const oldPrice = Number(product.retail_price);
  const [name, setName] = useState(product.name);
  const [price, setPrice] = useState<number | null>(oldPrice);
  const [quantity, setQuantity] = useState<string | null>(null);
  const [date, setDate] = useState(todayInput);
  const [closedOn, setClosedOn] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // the day the period is closed on, a revaluation may not be dated before it
  useEffect(() => {
    let current = true;
    getBalance(null)
      .then((balance) => current && setClosedOn(balance.closed_on))
      .catch(() => current && setClosedOn(null));
    return () => {
      current = false;
    };
  }, []);

  const nameChanged = name.trim() !== product.name;
  const priceChanged = price !== null && price !== oldPrice;
  // no old stock on the shelf, the price changes without a ledger entry
  const noStock = quantity === null || (QUANTITY.test(quantity) && Number(quantity) === 0);
  const revalue = priceChanged && !noStock;
  const valid =
    name.trim() !== "" &&
    price !== null &&
    price > 0 &&
    (nameChanged || priceChanged) &&
    (!revalue || (quantity !== null && QUANTITY.test(quantity) && fromInputDate(date) !== null));
  const amount =
    revalue && valid && price !== null ? Number(quantity) * (price - oldPrice) : null;

  async function submit() {
    if (!valid || busy || price === null) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const posted = await editProduct(product.id, {
        name: name.trim(),
        retail_price: price,
        revaluation: revalue
          ? {
              occurred_on: fromInputDate(date) ?? "",
              quantity: quantity ?? "",
              comment: toText(comment),
            }
          : null,
      });
      onSaved(posted);
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="modal-form modal-product">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">Товар</h2>
          <p className="modal-text">
            Старое название останется другим написанием, по нему товар найдётся в следующих
            накладных.
          </p>
          <div className="fields">
            <label className="field">
              <span className="field-label">Название</span>
              <input
                className="input"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>

            <div className="field-row">
              <label className="field">
                <span className="field-label">Цена, ₽ (была {formatNumber(oldPrice)})</span>
                <input
                  className="input"
                  inputMode="numeric"
                  required
                  value={price ?? ""}
                  onChange={(event) => setPrice(toRubles(event.target.value))}
                />
              </label>
              {priceChanged && (
                <label className="field field-grow">
                  <span className="field-label">Осталось старого товара</span>
                  <input
                    className="input"
                    inputMode="decimal"
                    placeholder={product.unit ? `${product.unit}, пусто если нет` : "пусто, если нет"}
                    value={quantity ?? ""}
                    onChange={(event) => setQuantity(toDecimal(event.target.value))}
                  />
                </label>
              )}
            </div>

            {revalue && (
              <div className="field-row">
                <label className="field">
                  <span className="field-label">Дата переоценки</span>
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
            )}

            {priceChanged && (
              <dl className="stocktake-preview">
                <div>
                  <dt>Остаток изменится на</dt>
                  <dd>
                    {!revalue ? "не изменится" : amount === null ? "—" : `${formatSigned(amount)} ₽`}
                  </dd>
                </div>
                <div>
                  <dt>В журнал</dt>
                  <dd>{revalue ? "переоценка" : "ничего"}</dd>
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
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}
