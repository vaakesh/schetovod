import { useEffect, useRef, useState } from "react";

import { addLedgerBatch, getBalance, getLedgerComments } from "../api";
import { calculate } from "../calc";
import { AMOUNT, fromInputDate, todayInput, toInputDate, toText } from "../form";
import { formatMoney } from "../format";
import { message } from "../message";
import type { BatchKind, LedgerBalance } from "../types";
import CalcInput from "./CalcInput";
import Icon from "./icons";
import Modal from "./Modal";

interface Props {
  kind: BatchKind;
  onClose: () => void;
  onPosted: () => void;
}

interface Row {
  id: number;
  date: string;
  amount: string;
  comment: string;
}

const TITLES: Record<BatchKind, string> = {
  write_off: "Списание",
  stock_in: "Приход товара",
  cash_in: "Внесение в кассу",
  cash_out: "Выдача из кассы",
};

const COMMENT_HINTS: Record<BatchKind, string> = {
  write_off: "Например, бой или просрочка",
  stock_in: "Например, из мяса или обмен",
  cash_in: "Например, размен",
  cash_out: "Например, забрал владелец или накладная № 17",
};

export default function LedgerBatchDialog({ kind, onClose, onPosted }: Props) {
  const form = useRef<HTMLFormElement>(null);
  const nextId = useRef(1);
  const [rows, setRows] = useState<Row[]>([
    { id: 0, date: todayInput(), amount: "", comment: "" },
  ]);
  const [books, setBooks] = useState<LedgerBalance | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const cash = kind === "cash_in" || kind === "cash_out";
  const commentRequired = kind === "cash_out";
  const minDate = toInputDate((cash ? books?.cash_closed_on : books?.closed_on) ?? null);
  const values = rows.map((row) => calculate(row.amount));
  const total = values.reduce((sum, value) => sum + Number(value), 0);
  const valid = rows.every(
    (row, index) =>
      row.date !== "" &&
      AMOUNT.test(values[index] ?? "") &&
      Number(values[index]) > 0 &&
      (!commentRequired || toText(row.comment) !== null),
  );

  // opening a modal moves the focus to its first field, the date is right more often than the sum
  useEffect(() => {
    form.current?.querySelector<HTMLInputElement>(".input-money")?.focus();
  }, []);

  // the closing days do not depend on the date of a line
  useEffect(() => {
    let current = true;
    getBalance(null)
      .then((balance) => current && setBooks(balance))
      .catch(() => current && setBooks(null));
    // the buttons are a shortcut, the comment is typed without them
    getLedgerComments(kind)
      .then((comments) => current && setHints(comments))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [kind]);

  function change(id: number, changes: Partial<Row>) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...changes } : row)));
  }

  // usually the same day goes on, so the new line takes the date of the last one
  function add() {
    const id = nextId.current;
    nextId.current += 1;
    setRows((current) => [
      ...current,
      { id, date: current[current.length - 1]?.date ?? todayInput(), amount: "", comment: "" },
    ]);
  }

  function remove(id: number) {
    setRows((current) => current.filter((row) => row.id !== id));
  }

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addLedgerBatch(
        kind,
        rows.map((row, index) => ({
          occurred_on: fromInputDate(row.date),
          amount: values[index] ?? null,
          comment: toText(row.comment),
        })),
      );
      onPosted();
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="modal-form modal-batch">
      <form
        ref={form}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">{TITLES[kind]}</h2>
          <div className="batch-rows">
            {rows.map((row, index) => (
              <section key={row.id} className="batch-row" aria-label={`Операция ${index + 1}`}>
                {rows.length > 1 && (
                  <div className="batch-row-head">
                    <span className="field-label">Операция {index + 1}</span>
                    <button
                      type="button"
                      className="row-delete"
                      aria-label={`Убрать операцию ${index + 1}`}
                      title="Убрать"
                      onClick={() => remove(row.id)}
                    >
                      <Icon name="close" size={16} />
                    </button>
                  </div>
                )}
                <div className="field-pair">
                  <label className="field">
                    <span className="field-label">Дата</span>
                    <input
                      className="input"
                      type="date"
                      required
                      value={row.date}
                      max={todayInput()}
                      min={minDate || undefined}
                      onChange={(event) => change(row.id, { date: event.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Сумма, ₽</span>
                    <CalcInput
                      autoFocus
                      value={row.amount}
                      onChange={(amount) => change(row.id, { amount })}
                    />
                  </label>
                </div>
                <label className="field">
                  <span className="field-label">{commentRequired ? "На что" : "Комментарий"}</span>
                  <input
                    className="input"
                    required={commentRequired}
                    placeholder={COMMENT_HINTS[kind]}
                    value={row.comment}
                    onChange={(event) => change(row.id, { comment: event.target.value })}
                  />
                </label>
                {hints.length > 0 && (
                  <div className="comment-hints">
                    {hints.map((hint) => (
                      <button
                        key={hint}
                        type="button"
                        className={row.comment === hint ? "comment-hint active" : "comment-hint"}
                        aria-pressed={row.comment === hint}
                        onClick={() => change(row.id, { comment: hint })}
                      >
                        {hint}
                      </button>
                    ))}
                  </div>
                )}
              </section>
            ))}
          </div>
          <button type="button" className="button button-soft batch-add" onClick={add}>
            <Icon name="plus" size={18} />
            Ещё операция
          </button>
          {rows.length > 1 && (
            <dl className="stocktake-preview">
              <div>
                <dt>Операций</dt>
                <dd>{rows.length}</dd>
              </div>
              <div>
                <dt>На сумму</dt>
                <dd>{valid ? `${formatMoney(total)} ₽` : "—"}</dd>
              </div>
            </dl>
          )}
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={!valid || busy}>
            {rows.length > 1 ? `Записать ${rows.length}` : "Записать"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
