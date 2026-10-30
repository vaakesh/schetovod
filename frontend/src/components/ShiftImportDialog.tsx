import { useState } from "react";

import { importShifts } from "../api";
import { formatDate, formatMoney } from "../format";
import { fromInputDate, todayInput } from "../form";
import { message } from "../message";
import type { ShiftImportResult } from "../types";
import Modal from "./Modal";

interface Props {
  onClose: () => void;
  onImported: (entryIds: number[]) => void;
}

export default function ShiftImportDialog({ onClose, onImported }: Props) {
  const [dateFrom, setDateFrom] = useState(todayInput);
  const [dateTo, setDateTo] = useState(todayInput);
  const [result, setResult] = useState<ShiftImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = fromInputDate(dateFrom);
  const to = fromInputDate(dateTo);
  // a date input compares as text
  const valid = from !== null && to !== null && dateFrom <= dateTo;

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const loaded = await importShifts(from, to);
      setResult(loaded);
      onImported(loaded.imported.map((shift) => shift.entry_id));
    } catch (reason) {
      setError(message(reason));
    } finally {
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
          <h2 className="modal-title">Загрузка смен из кассы</h2>
          <div className="fields">
            <div className="field-pair">
              <label className="field">
                <span className="field-label">С</span>
                <input
                  className="input"
                  type="date"
                  required
                  value={dateFrom}
                  max={dateTo}
                  onChange={(event) => setDateFrom(event.target.value)}
                />
              </label>
              <label className="field">
                <span className="field-label">По</span>
                <input
                  className="input"
                  type="date"
                  required
                  value={dateTo}
                  min={dateFrom}
                  max={todayInput()}
                  onChange={(event) => setDateTo(event.target.value)}
                />
              </label>
            </div>
          </div>
          {result && (
            <div className="shift-import">
              {result.imported.length === 0 && result.skipped.length === 0 && (
                <p className="shift-import-empty">За этот период смен с продажами нет</p>
              )}
              {result.imported.length > 0 && (
                <>
                  <h3 className="shift-import-title">Загружено</h3>
                  <ul className="shift-import-list">
                    {result.imported.map((shift) => (
                      <li key={shift.entry_id} className="shift-import-row">
                        <span>
                          №{shift.shift_number} от {formatDate(shift.occurred_on)}
                        </span>
                        <span className="shift-import-sums">
                          нал {formatMoney(shift.cash)} ₽, безнал {formatMoney(shift.card)} ₽
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {result.skipped.length > 0 && (
                <>
                  <h3 className="shift-import-title">Пропущено</h3>
                  <ul className="shift-import-list">
                    {result.skipped.map((shift) => (
                      <li key={shift.shift_number} className="shift-import-row">
                        <span>
                          №{shift.shift_number}
                          {shift.occurred_on && ` от ${formatDate(shift.occurred_on)}`}
                        </span>
                        <span className="shift-import-reason">{shift.reason}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" onClick={onClose}>
            Закрыть
          </button>
          <button type="submit" className="button button-primary" disabled={!valid || busy}>
            {busy ? "Загружаем…" : "Загрузить"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
