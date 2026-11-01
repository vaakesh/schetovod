import { useMemo, useState } from "react";

import { addExpense, editExpense } from "../api";
import { AMOUNT, toDecimal, trimDecimal } from "../form";
import { message } from "../message";
import { BASES, currentMonth, isPercent, monthLabel, monthRange, shiftMonth } from "../profit";
import type { ExpenseBasis, ExpenseForm, ExpenseOut, ProfitReport } from "../types";
import Modal from "./Modal";

// a rate may be planned for a few months ahead
const MONTHS_AHEAD = 3;
const MONTHS_BACK = 12;

interface Props {
  // null adds a new expense
  expense: ExpenseOut | null;
  onClose: () => void;
  onSaved: (report: ProfitReport) => void;
}

export default function ExpenseDialog({ expense, onClose, onSaved }: Props) {
  const thisMonth = currentMonth();
  const [name, setName] = useState(expense?.name ?? "");
  const [basis, setBasis] = useState<ExpenseBasis>(expense?.basis ?? "month");
  const [amount, setAmount] = useState(trimDecimal(expense?.amount ?? null) ?? "");
  // a change starts from this month, the past keeps the old rate
  const [startsOn, setStartsOn] = useState(() => {
    const oldest = expense?.starts_on ?? thisMonth;
    return monthRange(thisMonth, oldest).length > 1 ? oldest : thisMonth;
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const months = useMemo(
    () =>
      monthRange(
        expense?.starts_on ?? shiftMonth(thisMonth, -MONTHS_BACK),
        shiftMonth(thisMonth, MONTHS_AHEAD),
      ),
    [expense?.starts_on, thisMonth],
  );

  const decimal = toDecimal(amount);
  const percent = isPercent(basis);
  const sensible =
    decimal !== null &&
    AMOUNT.test(decimal) &&
    Number(decimal) > 0 &&
    (!percent || Number(decimal) <= 100);
  const changed =
    expense === null ||
    name.trim() !== expense.name ||
    basis !== expense.basis ||
    Number(decimal) !== Number(expense.amount);
  const valid = name.trim() !== "" && sensible && changed;
  const unit = BASES.find((item) => item.value === basis)?.unit;

  async function submit() {
    if (!valid || busy || decimal === null) {
      return;
    }
    const body: ExpenseForm = {
      name: name.trim(),
      basis,
      amount: decimal,
      starts_on: startsOn,
    };
    setBusy(true);
    setError(null);
    try {
      onSaved(await (expense ? editExpense(expense.id, body) : addExpense(body)));
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
          <h2 className="modal-title">{expense ? expense.name : "Новый расход"}</h2>
          <p className="modal-text">
            {expense && startsOn === expense.starts_on
              ? "Сумма заменится с самого начала, прошлые месяцы пересчитаются."
              : "Месяцы до выбранного останутся посчитанными как раньше."}
          </p>
          <div className="fields">
            <label className="field">
              <span className="field-label">Название</span>
              <input
                className="input"
                required
                autoFocus={expense === null}
                placeholder="Например, вывоз мусора"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <div className="field-row">
              <label className="field field-grow">
                <span className="field-label">Как считать</span>
                <select
                  className="input"
                  value={basis}
                  onChange={(event) => setBasis(event.target.value as ExpenseBasis)}
                >
                  {BASES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field field-grow">
                <span className="field-label">{percent ? "Процент" : "Сумма"}, {unit}</span>
                <input
                  className="input"
                  required
                  inputMode="decimal"
                  autoFocus={expense !== null}
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span className="field-label">Действует с</span>
              <select
                className="input"
                value={startsOn}
                onChange={(event) => setStartsOn(event.target.value)}
              >
                {months.map((month) => (
                  <option key={month} value={month}>
                    {monthLabel(month)}
                  </option>
                ))}
              </select>
            </label>
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
