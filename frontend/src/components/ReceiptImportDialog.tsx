import { useState } from "react";

import { importReceipts } from "../api";
import { todayInput } from "../form";
import { formatNumber } from "../format";
import { message } from "../message";
import { monthsOf } from "../traffic";
import type { ReceiptImportResult } from "../types";
import Modal from "./Modal";

interface Props {
  // the day to go on from
  start: string;
  onClose: () => void;
  onImported: () => void;
}

export default function ReceiptImportDialog({ start, onClose, onImported }: Props) {
  const [dateFrom, setDateFrom] = useState(start);
  const [dateTo, setDateTo] = useState(todayInput);
  const [result, setResult] = useState<ReceiptImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // the month being loaded and how many there are, null while idle
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const busy = progress !== null;
  // a date input compares as text
  const valid = dateFrom !== "" && dateTo !== "" && dateFrom <= dateTo;

  async function submit() {
    if (!valid || busy) {
      return;
    }
    const months = monthsOf(dateFrom, dateTo);
    const total: ReceiptImportResult = { received: 0, loaded: 0, present: 0 };
    setError(null);
    setResult(null);
    try {
      for (const [index, month] of months.entries()) {
        setProgress({ done: index + 1, total: months.length });
        const loaded = await importReceipts(month.from, month.to);
        total.received += loaded.received;
        total.loaded += loaded.loaded;
        total.present += loaded.present;
        setResult({ ...total });
      }
    } catch (reason) {
      setError(message(reason));
    } finally {
      setProgress(null);
      // the months before a failure are saved
      onImported();
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
          <h2 className="modal-title">Загрузка чеков из кассы</h2>
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
              {result.received === 0 ? (
                <p className="shift-import-empty">За этот период чеков нет</p>
              ) : (
                <ul className="shift-import-list">
                  <li className="shift-import-row">
                    <span>Загружено новых</span>
                    <span className="shift-import-sums">{formatNumber(result.loaded)}</span>
                  </li>
                  <li className="shift-import-row">
                    <span>Уже были загружены</span>
                    <span className="shift-import-sums">{formatNumber(result.present)}</span>
                  </li>
                </ul>
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
            {progress
              ? `Загружаем${progress.total > 1 ? ` ${progress.done} из ${progress.total}` : ""}…`
              : "Загрузить"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
