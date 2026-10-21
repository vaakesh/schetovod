import { useEffect, useState } from "react";

import { confirmInvoice, getBalance } from "../api";
import { fromInputDate, toInputDate, todayInput } from "../form";
import { message } from "../message";
import type { ConfirmedInvoice } from "../types";
import Modal from "./Modal";

interface Props {
  invoiceId: number;
  // the date printed on the invoice, the goods usually come on it
  invoiceDate: string | null;
  onClose: () => void;
  onConfirmed: (result: ConfirmedInvoice) => void;
}

// the invoice date unless it is missing or in the future, a date input compares as text
function initialDate(invoiceDate: string | null): string {
  const today = todayInput();
  const printed = toInputDate(invoiceDate);
  return printed && printed <= today ? printed : today;
}

export default function InvoiceConfirmDialog({ invoiceId, invoiceDate, onClose, onConfirmed }: Props) {
  const [date, setDate] = useState(() => initialDate(invoiceDate));
  const [closedOn, setClosedOn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // the inflow may not be dated before the latest stocktake
  useEffect(() => {
    let current = true;
    getBalance(null)
      .then((balance) => current && setClosedOn(balance.closed_on))
      .catch(() => current && setClosedOn(null));
    return () => {
      current = false;
    };
  }, []);

  async function submit() {
    const occurredOn = fromInputDate(date);
    if (!occurredOn || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onConfirmed(await confirmInvoice(invoiceId, occurredOn));
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
          <h2 className="modal-title">Провести накладную</h2>
          <div className="fields">
            <label className="field">
              <span className="field-label">Дата прихода</span>
              <input
                className="input"
                type="date"
                required
                autoFocus
                value={date}
                max={todayInput()}
                min={toInputDate(closedOn) || undefined}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
          </div>
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={!date || busy}>
            Провести
          </button>
        </div>
      </form>
    </Modal>
  );
}
