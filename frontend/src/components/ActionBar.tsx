import type { InvoiceDraft } from "../types";

interface Props {
  draft: InvoiceDraft;
  dirty: boolean;
  busy: boolean;
  error: string | null;
  onSave: () => void;
  onReset: () => void;
  onConfirm: () => void;
  onDecline: () => void;
}

function hint(draft: InvoiceDraft, dirty: boolean): string {
  if (dirty) {
    return "Есть несохранённые правки";
  }
  const blocking = draft.issues.filter((issue) => issue.blocking).length;
  if (blocking > 0) {
    return `Осталось исправить: ${blocking}`;
  }
  return "Всё сходится";
}

function tone(draft: InvoiceDraft, dirty: boolean): string {
  if (dirty) {
    return "dock-hint hint-pending";
  }
  return draft.ready ? "dock-hint hint-ok" : "dock-hint hint-bad";
}

export default function ActionBar({
  draft,
  dirty,
  busy,
  error,
  onSave,
  onReset,
  onConfirm,
  onDecline,
}: Props) {
  return (
    <div className="dock">
      {error && <pre className="dock-error">{error}</pre>}
      <div className="dock-bar">
        <span className={tone(draft, dirty)}>{hint(draft, dirty)}</span>
        {dirty ? (
          <>
            <button type="button" className="button button-ghost" disabled={busy} onClick={onReset}>
              Отменить
            </button>
            <button type="button" className="button button-primary" disabled={busy} onClick={onSave}>
              Сохранить
            </button>
          </>
        ) : (
          <>
            <button type="button" className="button button-ghost" disabled={busy} onClick={onDecline}>
              Отклонить
            </button>
            <button
              type="button"
              className="button button-primary"
              disabled={busy || !draft.ready}
              onClick={onConfirm}
            >
              Провести
            </button>
          </>
        )}
      </div>
    </div>
  );
}
