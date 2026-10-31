import { useEffect, useState } from "react";

import type { Slot, SlotStatus } from "../batch";
import { formatDate, formatMoney, formatText, plural } from "../format";
import type { InvoiceDraft } from "../types";
import Icon from "./icons";

const STATUS_LABELS: Record<SlotStatus, string> = {
  filling: "",
  queued: "В очереди",
  sending: "В работе",
  done: "Готово",
  failed: "Ошибка",
};

function Thumb({ file, onRemove }: { file: File; onRemove: (() => void) | null }) {
  const [url, setUrl] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);

  // the address is created here to be released together with the thumbnail
  useEffect(() => {
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);

  return (
    <div className="slot-thumb" title={file.name}>
      {url && !broken ? (
        <img src={url} alt={file.name} onError={() => setBroken(true)} />
      ) : (
        <Icon name="photo" />
      )}
      {onRemove && (
        <button
          type="button"
          className="slot-thumb-remove"
          aria-label={`Убрать ${file.name}`}
          onClick={onRemove}
        >
          <Icon name="close" size={14} />
        </button>
      )}
    </div>
  );
}

function Summary({ draft }: { draft: InvoiceDraft }) {
  const lines = draft.lines.length;
  const number = draft.form.invoice_number;
  const date = draft.form.invoice_date;
  const total = draft.totals.cost_total;
  return (
    <div className="slot-summary">
      <p className="slot-supplier">
        {formatText(draft.supplier?.name ?? draft.extraction.supplier.name)}
      </p>
      <p className="slot-meta">
        {[number && `№${number}`, date && formatDate(date)].filter(Boolean).join(" от ")}
      </p>
      <p className="slot-meta">
        {total !== null && `${formatMoney(total)} ₽ · `}
        {lines} {plural(lines, "строка", "строки", "строк")}
      </p>
    </div>
  );
}

interface Props {
  slot: Slot;
  number: number;
  onPick: () => void;
  onRemoveFile: (file: File) => void;
  onRemove: () => void;
  onRetry: () => void;
  onOpen: (id: number) => void;
}

export default function InvoiceSlot({
  slot,
  number,
  onPick,
  onRemoveFile,
  onRemove,
  onRetry,
  onOpen,
}: Props) {
  const { status, files, draft, error, refused } = slot;
  const editable = status === "filling" || status === "failed";

  return (
    <section className={`slot slot-${status}`} aria-label={`Накладная ${number}`}>
      <header className="slot-head">
        <h2 className="slot-title">Накладная {number}</h2>
        <span className="slot-status" aria-live="polite">
          {status !== "filling" && <span className="slot-status-text">{STATUS_LABELS[status]}</span>}
          {status === "queued" && <span className="slot-mark slot-mark-queued" />}
          {status === "sending" && <span className="spinner slot-spinner" />}
          {status === "done" && (
            <span className="slot-mark slot-mark-done">
              <Icon name="check" size={18} />
            </span>
          )}
          {status === "failed" && (
            <span className="slot-mark slot-mark-failed">
              <Icon name="alert" size={18} />
            </span>
          )}
        </span>
      </header>

      <div className="slot-photos">
        {files.map((file) => (
          <Thumb
            // the same photo may be picked twice, a File is unique as an object only
            key={`${file.name}-${file.size}-${file.lastModified}-${files.indexOf(file)}`}
            file={file}
            onRemove={editable ? () => onRemoveFile(file) : null}
          />
        ))}
        {editable && (
          <button type="button" className="slot-add" aria-label="Добавить фото" onClick={onPick}>
            <Icon name="plus" />
          </button>
        )}
      </div>

      {draft && <Summary draft={draft} />}
      {error && <pre className="slot-error">{error}</pre>}
      {refused && <pre className="slot-error">{refused}</pre>}

      <footer className="slot-foot">
        {status === "filling" && <span className="slot-meta">{files.length} фото</span>}
        {status === "sending" && <span className="slot-meta">Распознаём {files.length} фото</span>}
        {draft && (
          <button
            type="button"
            className="button button-soft"
            aria-label={`Открыть черновик накладной ${number}`}
            onClick={() => onOpen(draft.id)}
          >
            Открыть
          </button>
        )}
        {status === "failed" && (
          <button
            type="button"
            className="button button-soft"
            disabled={files.length === 0}
            onClick={onRetry}
          >
            Повторить
          </button>
        )}
        {status !== "sending" && (
          <button type="button" className="button button-ghost slot-remove" onClick={onRemove}>
            Убрать
          </button>
        )}
      </footer>
    </section>
  );
}
