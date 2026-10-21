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
  sale: "Продажа",
  write_off: "Списание",
  stocktake: "Переучёт",
  cash_in: "Внесение в кассу",
  cash_out: "Выдача из кассы",
  cash_count: "Сверка кассы",
};

const COMMENT_HINTS: Record<ManualKind, string> = {
  sale: "Например, выручка за смену",
  write_off: "Например, бой или просрочка",
  stocktake: "Например, плановый переучёт",
  cash_in: "Например, размен",
  cash_out: "Например, забрал владелец или накладная № 17",
  cash_count: "Например, пересчёт в конце смены",
};

const AMOUNT_LABELS: Record<ManualKind, string> = {
  sale: "Наличные, ₽",
  write_off: "Сумма, ₽",
  stocktake: "Насчитали, ₽",
  cash_in: "Сумма, ₽",
  cash_out: "Сумма, ₽",
  cash_count: "В кассе по факту, ₽",
};

// the till kinds never touch the stock, a sale touches both
const CASH_ONLY: ManualKind[] = ["cash_in", "cash_out", "cash_count"];

// rubles with at most two decimals, the api rejects anything else
const AMOUNT = /^\d+(\.\d{1,2})?$/;

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
  const value = toDecimal(amount) ?? (sale ? "0" : null);
  const cardValue = toDecimal(card) ?? "0";
  const total = Number(value) + (sale ? Number(cardValue) : 0);
  const commentRequired = kind === "cash_out";
  const valid =
    value !== null &&
    AMOUNT.test(value) &&
    (!sale || AMOUNT.test(cardValue)) &&
    (count || total > 0) &&
    (!commentRequired || toText(comment) !== null);

  const touchesStock = !CASH_ONLY.includes(kind);
  const touchesCash = CASH_ONLY.includes(kind) || (sale && Number(value) > 0);
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
                <input
                  className="input input-money"
                  inputMode="decimal"
                  autoFocus
                  placeholder="0,00"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </label>
              {sale && (
                <label className="field">
                  <span className="field-label">Безнал, ₽</span>
                  <input
                    className="input input-money"
                    inputMode="decimal"
                    placeholder="0,00"
                    value={card}
                    onChange={(event) => setCard(event.target.value)}
                  />
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
              <span className="field-label">{commentRequired ? "На что" : "Комментарий"}</span>
              <input
                className="input"
                required={commentRequired}
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
