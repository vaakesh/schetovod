import { useEffect, useRef, useState } from "react";

import { deleteProductAlias, editProduct, getBalance } from "../api";
import { formatNumber, formatSigned } from "../format";
import {
  fromInputDate,
  QUANTITY,
  toDecimal,
  toInputDate,
  todayInput,
  toRubles,
  toText,
} from "../form";
import { message } from "../message";
import type { CatalogAlias, CatalogProduct, LedgerPosted } from "../types";
import type { Ask } from "./ConfirmDialog";
import Modal from "./Modal";

interface Props {
  product: CatalogProduct;
  ask: Ask;
  onClose: () => void;
  onAliasRemoved: (productId: number, aliasId: number) => void;
  // null when the price changed without a revaluation
  onSaved: (posted: LedgerPosted | null) => void;
}

export default function ProductEditDialog({ product, ask, onClose, onAliasRemoved, onSaved }: Props) {
  const [original] = useState(() => ({ name: product.name, price: Number(product.retail_price) }));
  const oldPrice = original.price;
  const [name, setName] = useState(original.name);
  const [price, setPrice] = useState<number | null>(oldPrice);
  const [quantity, setQuantity] = useState<string | null>(null);
  const [date, setDate] = useState(todayInput);
  const [closedOn, setClosedOn] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deletingAlias, setDeletingAlias] = useState<number | null>(null);
  const [aliasError, setAliasError] = useState<string | null>(null);
  const aliasesHeading = useRef<HTMLHeadingElement>(null);
  const deleting = deletingAlias !== null;

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

  const nameChanged = name.trim() !== original.name;
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
    if (!valid || busy || deleting || price === null) {
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

  async function removeAlias(alias: CatalogAlias) {
    if (busy || deleting) {
      return;
    }
    const confirmed = await ask({
      title: "Удалить другое название?",
      text: `«${product.name}» больше не будет находиться по названию «${alias.name}».`,
      action: "Удалить",
      danger: true,
    });
    if (!confirmed) {
      return;
    }

    setDeletingAlias(alias.id);
    setAliasError(null);
    try {
      await deleteProductAlias(product.id, alias.id);
      onAliasRemoved(product.id, alias.id);
      aliasesHeading.current?.focus();
    } catch (reason) {
      setAliasError(message(reason));
    } finally {
      setDeletingAlias(null);
    }
  }

  function close() {
    if (!deleting) {
      onClose();
    }
  }

  return (
    <Modal label="Товар" onClose={close} className="modal-form modal-product">
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

            {priceChanged && product.has_price_tag && (
              <p className="modal-text">Отметка о ценнике снимется — повесьте новый.</p>
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
          <section className="product-aliases" aria-labelledby="product-aliases-title">
            <h3 id="product-aliases-title" ref={aliasesHeading} tabIndex={-1}>
              Другие названия
            </h3>
            {product.aliases.length ? (
              <ul className="product-alias-list">
                {product.aliases.map((alias) => (
                  <li key={alias.id}>
                    <span>{alias.name}</span>
                    <button
                      type="button"
                      className="button button-ghost"
                      aria-label={`${deletingAlias === alias.id ? "Удаляем" : "Удалить"} «${alias.name}»`}
                      disabled={busy || deleting}
                      onClick={() => void removeAlias(alias)}
                    >
                      {deletingAlias === alias.id ? "Удаляем…" : "Удалить"}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="modal-text">Нет других названий.</p>
            )}
            {aliasError && (
              <p className="modal-error" role="alert">{aliasError}</p>
            )}
          </section>
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" disabled={deleting} onClick={close}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={!valid || busy || deleting}>
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}
