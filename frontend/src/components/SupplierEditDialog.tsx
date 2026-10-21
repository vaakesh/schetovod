import { useState } from "react";

import { editSupplier } from "../api";
import { toText } from "../form";
import { message } from "../message";
import type { SupplierEdit, SupplierSummary } from "../types";
import Modal from "./Modal";

interface Props {
  supplier: SupplierSummary;
  onClose: () => void;
  onSaved: () => void;
}

export default function SupplierEditDialog({ supplier, onClose, onSaved }: Props) {
  const [name, setName] = useState(supplier.name);
  const [shortName, setShortName] = useState(supplier.short_name ?? "");
  const [inn, setInn] = useState(supplier.inn ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // an empty field clears the short name, the reports then print the full one
  const value: SupplierEdit = {
    name: name.trim(),
    short_name: toText(shortName.trim()),
    inn: toText(inn.trim()),
  };
  const changed =
    value.name !== supplier.name ||
    value.short_name !== supplier.short_name ||
    value.inn !== supplier.inn;
  const valid = value.name !== "" && changed;

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await editSupplier(supplier.id, value);
      onSaved();
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
          <h2 className="modal-title">{supplier.name}</h2>
          <p className="modal-text">
            Короткое имя печатается в отчётах вместо полного. Если поле пустое, в отчёте будет
            полное имя.
          </p>
          <div className="fields">
            <label className="field">
              <span className="field-label">Полное имя</span>
              <input
                className="input"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Короткое имя для отчётов</span>
              <input
                className="input"
                autoFocus
                placeholder="Например, Ромашка"
                value={shortName}
                onChange={(event) => setShortName(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">ИНН</span>
              <input
                className="input"
                inputMode="numeric"
                placeholder="10 или 12 цифр"
                value={inn}
                onChange={(event) => setInn(event.target.value)}
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
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}
