import { useEffect, useState } from "react";

import { addLedgerEntry, getBalance } from "../api";
import { calculate } from "../calc";
import { formatMoney, formatSigned } from "../format";
import { AMOUNT, fromInputDate, toInputDate, todayInput, toText } from "../form";
import { message } from "../message";
import type { LedgerBalance, SingleKind } from "../types";
import CalcInput from "./CalcInput";
import Modal from "./Modal";

interface Props {
  kind: SingleKind;
  onClose: () => void;
  onPosted: () => void;
}

const TITLES: Record<SingleKind, string> = {
  sale: "Продажа",
  stocktake: "Переучёт",
  cash_count: "Сверка кассы",
};

const COMMENT_HINTS: Record<SingleKind, string> = {
  sale: "Например, выручка за смену",
  stocktake: "Например, плановый переучёт",
  cash_count: "Например, пересчёт в конце смены",
};

const AMOUNT_LABELS: Record<SingleKind, string> = {
  sale: "Наличные, ₽",
  stocktake: "Насчитали, ₽",
  cash_count: "В кассе по факту, ₽",
};

// a field may still hold an expression, an empty one has its own meaning
function fieldValue(text: string, empty: string | null): string | null {
  return text.trim() === "" ? empty : calculate(text);
}

// the later of the closing days, a date input compares as text
function latest(days: (string | null | undefined)[]): string {
  return days.map((day) => toInputDate(day ?? null)).reduce((a, b) => (a > b ? a : b), "");
}

export default function LedgerEntryDialog({ kind, onClose, onPosted }: Props) {
  const [date, setDate] = useState(todayInput);
  const [amount, setAmount] = useState("");
  const [card, setCard] = useState("");
  const [comment, setComment] = useState("");
  const [books, setBooks] = useState<LedgerBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sale = kind === "sale";
  const count = kind === "stocktake" || kind === "cash_count";
  // an empty part of a sale is zero, the other part may hold the whole sale
  const value = fieldValue(amount, sale ? "0" : null);
  const cardValue = fieldValue(card, "0");
  const total = Number(value) + (sale ? Number(cardValue) : 0);
  const valid =
    value !== null &&
    AMOUNT.test(value) &&
    (!sale || (cardValue !== null && AMOUNT.test(cardValue))) &&
    (count || total > 0);

  // a sale touches both the stock and the till
  const touchesStock = kind !== "cash_count";
  const touchesCash = kind === "cash_count" || (sale && Number(value) > 0);
  const minDate = latest([touchesStock ? books?.closed_on : null, touchesCash ? books?.cash_closed_on : null]);
  const expected = kind === "cash_count" ? books?.cash_balance : books?.balance;

  // the balances on the chosen day and the days the periods are closed on
  useEffect(() => {
    let current = true;
    getBalance(fromInputDate(date))
      .then((balance) => current && setBooks(balance))
      .catch(() => current && setBooks(null));
    return () => {
      current = false;
    };
  }, [date]);

  function body(): Record<string, string | null> {
    const base = { occurred_on: fromInputDate(date), comment: toText(comment) };
    if (sale) {
      return { ...base, cash: value, card: cardValue };
    }
    return { ...base, [count ? "counted" : "amount"]: value };
  }

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addLedgerEntry(kind, body());
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
                min={minDate || undefined}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <div className={sale ? "field-pair" : undefined}>
              <label className="field">
                <span className="field-label">{AMOUNT_LABELS[kind]}</span>
                <CalcInput autoFocus value={amount} onChange={setAmount} />
              </label>
              {sale && (
                <label className="field">
                  <span className="field-label">Безнал, ₽</span>
                  <CalcInput value={card} onChange={setCard} />
                </label>
              )}
            </div>
            {sale && (
              <dl className="stocktake-preview">
                <div>
                  <dt>Всего продано</dt>
                  <dd>{valid ? `${formatMoney(total)} ₽` : "—"}</dd>
                </div>
                <div>
                  <dt>В кассу</dt>
                  <dd>{valid ? `${formatMoney(value)} ₽` : "—"}</dd>
                </div>
              </dl>
            )}
            {count && expected !== undefined && (
              <dl className="stocktake-preview">
                <div>
                  <dt>По учёту</dt>
                  <dd>{formatMoney(expected)} ₽</dd>
                </div>
                <div>
                  <dt>Расхождение</dt>
                  <dd>{valid ? `${formatSigned(Number(value) - Number(expected))} ₽` : "—"}</dd>
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
