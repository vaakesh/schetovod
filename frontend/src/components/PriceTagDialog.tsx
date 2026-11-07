import { useState } from "react";

import { editPriceTag } from "../api";
import { message } from "../message";
import {
  ORIGIN_LABELS,
  SIZES,
  UNIT_LABELS,
  emptyRow,
  fillRow,
  rowFields,
  rowProblems,
  type FormRow,
  type RowField,
  type SizeKey,
} from "../priceTags";
import type { PriceTag, PriceTagOrigin, PriceTagUnit } from "../types";
import Modal from "./Modal";
import ToggleField from "./ToggleField";

interface Props {
  tag: PriceTag;
  onClose: () => void;
  onSaved: (tag: PriceTag) => void;
  onDelete: (tag: PriceTag) => void;
}

export default function PriceTagDialog({ tag, onClose, onSaved, onDelete }: Props) {
  const [row, setRow] = useState<FormRow>(() => fillRow(emptyRow(), tag));
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const problems = rowProblems(row);

  function update(change: Partial<FormRow>) {
    setRow((current) => ({ ...current, ...change }));
  }

  function invalid(field: RowField): string {
    return checked && problems.has(field) ? " cell-required" : "";
  }

  async function submit() {
    setChecked(true);
    if (problems.size > 0 || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await editPriceTag(tag.id, rowFields(row)));
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="modal-form price-tag-dialog">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="modal-body">
          <h2 className="modal-title">Ценник</h2>
          <p className="modal-text">Изменения попадут в подсказки при печати.</p>
          <div className="fields">
            <div className="field-row">
              <label className="field">
                <span className="field-label">Размер, см</span>
                <select
                  className={`input${invalid("size")}`}
                  value={row.size}
                  onChange={(event) => update({ size: event.target.value as SizeKey | "" })}
                >
                  <option value="">—</option>
                  {SIZES.map((size) => (
                    <option key={size.key} value={size.key}>
                      {size.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="field">
                <span className="field-label">Ед. изм.</span>
                <ToggleField<PriceTagUnit>
                  label="Единица"
                  value={row.unit}
                  options={UNIT_LABELS}
                  onChange={(unit) => update({ unit })}
                />
              </div>
              <label className="field field-grow">
                <span className="field-label">Граммовка</span>
                <input
                  className="input"
                  placeholder="напр. 500 г"
                  value={row.pack}
                  onChange={(event) => update({ pack: event.target.value })}
                />
              </label>
            </div>
            <label className="field">
              <span className="field-label">Название</span>
              <textarea
                className={`input price-tag-textarea${invalid("name")}`}
                rows={2}
                value={row.name}
                onChange={(event) => update({ name: event.target.value })}
              />
            </label>
            <label className="field">
              <span className="field-label">Подназвание</span>
              <textarea
                className="input price-tag-textarea"
                rows={2}
                placeholder="Жирность, вкус, сорт"
                value={row.subtitle}
                onChange={(event) => update({ subtitle: event.target.value })}
              />
            </label>
            <div className="field-row">
              <label className="field">
                <span className="field-label">Цена, руб.</span>
                <input
                  className={`input price-tag-price${invalid("rub")}`}
                  inputMode="numeric"
                  value={row.rub}
                  onChange={(event) => update({ rub: event.target.value })}
                />
              </label>
              <label className="field">
                <span className="field-label">коп.</span>
                <input
                  className={`input price-tag-kop${invalid("kop")}`}
                  inputMode="numeric"
                  placeholder="00"
                  maxLength={2}
                  value={row.kop}
                  onChange={(event) => update({ kop: event.target.value })}
                />
              </label>
            </div>
            <div className="field">
              <ToggleField<PriceTagOrigin>
                label="Подпись внизу"
                value={row.origin}
                options={ORIGIN_LABELS}
                onChange={(origin) => update({ origin })}
              />
              <input
                className={`input${invalid("originName")}`}
                aria-label={ORIGIN_LABELS[row.origin]}
                placeholder={row.origin === "country" ? "напр. Россия" : "Название или город"}
                value={row.originName}
                onChange={(event) => update({ originName: event.target.value })}
              />
            </div>
          </div>
          {checked && problems.size > 0 && (
            <pre className="modal-error">Заполните выделенные поля</pre>
          )}
          {error && <pre className="modal-error">{error}</pre>}
        </div>
        <div className="modal-actions">
          <button
            type="button"
            className="button button-ghost price-tag-delete"
            onClick={() => onDelete(tag)}
          >
            Удалить
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={busy}>
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}
