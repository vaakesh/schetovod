import { useState } from "react";

import { addPayment, deletePayment } from "../api";
import { formatDate, formatMoney, formatText } from "../format";
import { fromInputDate, toDecimal, todayInput, toText, trimDecimal } from "../form";
import { message } from "../message";
import type { PostedInvoice } from "../types";
import { useConfirm } from "./ConfirmDialog";

interface Props {
  invoice: PostedInvoice;
  onChange: (invoice: PostedInvoice) => void;
}

// rubles with at most two decimals, the api rejects anything else
const AMOUNT = /^\d+(\.\d{1,2})?$/;

// the supplier may be paid in parts, the till is not touched
export default function PaymentsBlock({ invoice, onChange }: Props) {
  const [date, setDate] = useState(todayInput);
  // the whole debt by default, a part is typed over it
  const [amount, setAmount] = useState(() => trimDecimal(invoice.debt) ?? "");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ask, confirmElement] = useConfirm();

  const value = toDecimal(amount);
  const debt = Number(invoice.debt);
  const valid = value !== null && AMOUNT.test(value) && Number(value) > 0 && Number(value) <= debt;

  function update(next: PostedInvoice) {
    onChange(next);
    setAmount(trimDecimal(next.debt) ?? "");
    setComment("");
  }

  async function submit() {
    if (!valid || busy || value === null) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      update(
        await addPayment(invoice.id, {
          paid_on: fromInputDate(date),
          amount: value,
          comment: toText(comment),
        }),
      );
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function remove(paymentId: number, label: string) {
    const ok = await ask({
      title: "Удалить оплату?",
      text: label,
      action: "Удалить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setError(null);
    try {
      update(await deletePayment(invoice.id, paymentId));
    } catch (reason) {
      setError(message(reason));
    }
  }

  return (
    <section className="sheet payments">
      <h2 className="payments-title">Оплата поставщику</h2>
      <dl className="stocktake-preview">
        <div>
          <dt>К оплате</dt>
          <dd>{formatMoney(invoice.cost_total)} ₽</dd>
        </div>
        <div>
          <dt>Оплачено</dt>
          <dd>{formatMoney(invoice.paid)} ₽</dd>
        </div>
        <div>
          <dt>Долг</dt>
          <dd className={debt > 0 ? "payments-debt" : undefined}>{formatMoney(invoice.debt)} ₽</dd>
        </div>
      </dl>

      {invoice.payments.length > 0 && (
        <table className="list payments-list">
          <thead>
            <tr>
              <th>Дата</th>
              <th className="num">Сумма</th>
              <th>Комментарий</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invoice.payments.map((payment) => (
              <tr key={payment.id}>
                <td className="nowrap">{formatDate(payment.paid_on)}</td>
                <td className="num strong nowrap">{formatMoney(payment.amount)} ₽</td>
                <td>{formatText(payment.comment)}</td>
                <td className="num">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      void remove(
                        payment.id,
                        `${formatMoney(payment.amount)} ₽ от ${formatDate(payment.paid_on)}`,
                      )
                    }
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {debt > 0 && (
        <form
          className="field-row payments-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="field">
            <span className="field-label">Дата оплаты</span>
            <input
              className="input"
              type="date"
              required
              value={date}
              max={todayInput()}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Сумма, ₽</span>
            <input
              className="input input-money"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
          <label className="field field-grow">
            <span className="field-label">Комментарий</span>
            <input
              className="input"
              placeholder="Например, перевод с карты"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <button type="submit" className="button button-primary payments-submit" disabled={!valid || busy}>
            Записать оплату
          </button>
        </form>
      )}
      {error && <pre className="modal-error">{error}</pre>}
      {confirmElement}
    </section>
  );
}
