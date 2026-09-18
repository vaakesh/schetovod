import { useEffect, useState } from "react";

import { addLedgerEntry, getBalance } from "../api";
import { formatMoney, formatSigned } from "../format";
import { fromInputDate, toDecimal, toInputDate, todayInput, toText } from "../form";
import { message } from "../message";
import type { LedgerBalance, ManualKind } from "../types";
import Modal from "./Modal";

interface Props {
  kind: ManualKind;
  onClose: () => void;
  onPosted: () => void;
}

const TITLES: Record<ManualKind, string> = {
  sale: "Касса",
  write_off: "Списание",
  stocktake: "Переучёт",
};

const COMMENT_HINTS: Record<ManualKind, string> = {
  sale: "Например, выручка за смену",
  write_off: "Например, забрал владелец",
  stocktake: "Например, плановый переучёт",
};

// rubles with at most two decimals, the api rejects anything else
const AMOUNT = /^\d+(\.\d{1,2})?$/;

export default function LedgerEntryDialog({ kind, onClose, onPosted }: Props) {
  const [date, setDate] = useState(todayInput);
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [books, setBooks] = useState<LedgerBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const stocktake = kind === "stocktake";
  const value = toDecimal(amount);
  const valid = value !== null && AMOUNT.test(value) && (stocktake || Number(value) > 0);

  // the balance on the chosen day and the day the period is closed on
  useEffect(() => {
    let current = true;
    getBalance(fromInputDate(date))
      .then((balance) => current && setBooks(balance))
      .catch(() => current && setBooks(null));
    return () => {
      current = false;
    };
  }, [date]);

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addLedgerEntry(kind, {
        occurred_on: fromInputDate(date),
        [stocktake ? "counted" : "amount"]: value,
        comment: toText(comment),
      });
      onPosted();
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="modal-form">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">{TITLES[kind]}</h2>
          <div className="fields">
            <label className="field">
              <span className="field-label">Дата</span>
              <input
                className="input"
                type="date"
                required
                value={date}
                max={todayInput()}
                min={toInputDate(books?.closed_on ?? null) || undefined}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">{stocktake ? "Насчитали, ₽" : "Сумма, ₽"}</span>
              <input
                className="input input-money"
                inputMode="decimal"
                autoFocus
                placeholder="0,00"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </label>
            {stocktake && books && (
              <dl className="stocktake-preview">
                <div>
                  <dt>По учёту</dt>
                  <dd>{formatMoney(books.balance)} ₽</dd>
                </div>
                <div>
                  <dt>Расхождение</dt>
                  <dd>{valid ? `${formatSigned(Number(value) - Number(books.balance))} ₽` : "—"}</dd>
                </div>
              </dl>
            )}
            <label className="field">
              <span className="field-label">Комментарий</span>
              <input
                className="input"
                placeholder={COMMENT_HINTS[kind]}
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
            </label>
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
