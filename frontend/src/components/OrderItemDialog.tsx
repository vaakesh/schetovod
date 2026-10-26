import { useId, useState } from "react";

import { removeOrderItem, setOrderItem } from "../api";
import { formatMoney, formatNumber } from "../format";
import { QUANTITY, toDecimal, trimDecimal } from "../form";
import { message } from "../message";
import type { Order } from "../types";
import Modal from "./Modal";

export interface OrderTarget {
  productId: number;
  name: string;
  supplierName: string | null;
  unit: string | null;
  costPrice: string | null;
  // already in the cart, null while it is not
  quantity: string | null;
}

interface Props {
  target: OrderTarget;
  onClose: () => void;
  // the cart after the change, null when the last line is gone
  onSaved: (cart: Order | null, notice: string) => void;
}

// the steppers keep grams of a weighed product
function step(value: number, delta: number): string {
  return String(Math.round(Math.max(0, value + delta) * 1000) / 1000);
}

export default function OrderItemDialog({ target, onClose, onSaved }: Props) {
  const inputId = useId();
  const inCart = target.quantity !== null;
  const [text, setText] = useState(() => trimDecimal(target.quantity) ?? "1");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const quantity = toDecimal(text);
  const valid = quantity !== null && QUANTITY.test(quantity) && Number(quantity) > 0;
  const amount =
    valid && target.costPrice !== null ? Number(quantity) * Number(target.costPrice) : null;
  const current = valid ? Number(quantity) : 0;
  const unit = target.unit ? ` ${target.unit}` : "";
  const perUnit = target.unit ? ` за ${target.unit}` : "";

  async function run(send: () => Promise<Order | null>, notice: string) {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await send(), notice);
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  function submit() {
    if (!valid || quantity === null) {
      return;
    }
    void run(
      () => setOrderItem(target.productId, quantity),
      `«${target.name}» — ${formatNumber(quantity)}${unit} в заказе`,
    );
  }

  return (
    <Modal onClose={onClose} className="modal-form">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">{inCart ? "Количество в заказе" : "В заказ"}</h2>
          <p className="order-product">{target.name}</p>
          <p className="modal-text">
            {target.supplierName ?? "Поставщик неизвестен"}
            {" · "}
            {target.costPrice === null
              ? "ещё не закупался"
              : `закупка ${formatMoney(target.costPrice)} ₽${perUnit}`}
          </p>
          <div className="fields">
            {/* a label around the steppers would name the first of them, not the input */}
            <div className="field">
              <label className="field-label" htmlFor={inputId}>
                Количество{target.unit ? `, ${target.unit}` : ""}
              </label>
              <div className="order-qty">
                <button
                  type="button"
                  className="order-step"
                  aria-label="Меньше на 1"
                  disabled={current <= 1}
                  onClick={() => setText(step(current, -1))}
                >
                  −
                </button>
                <input
                  id={inputId}
                  className="input input-money order-qty-input"
                  inputMode="decimal"
                  autoFocus
                  required
                  value={text}
                  onFocus={(event) => event.target.select()}
                  onChange={(event) => setText(event.target.value)}
                />
                <button
                  type="button"
                  className="order-step"
                  aria-label="Больше на 1"
                  onClick={() => setText(step(current, 1))}
                >
                  +
                </button>
              </div>
            </div>
            <dl className="stocktake-preview">
              <div>
                <dt>Примерно на сумму</dt>
                <dd>
                  {amount !== null
                    ? `≈ ${formatMoney(amount)} ₽`
                    : target.costPrice === null
                      ? "цена неизвестна"
                      : "—"}
                </dd>
              </div>
            </dl>
          </div>
          {text !== "" && !valid && (
            <p className="modal-error">Число больше нуля, до трёх знаков после запятой</p>
          )}
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          {inCart && (
            <button
              type="button"
              className="button button-ghost order-remove"
              disabled={busy}
              onClick={() =>
                void run(
                  () => removeOrderItem(target.productId),
                  `«${target.name}» убран из заказа`,
                )
              }
            >
              Убрать из заказа
            </button>
          )}
          <button type="button" className="button button-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={!valid || busy}>
            {inCart ? "Сохранить" : "Добавить"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
