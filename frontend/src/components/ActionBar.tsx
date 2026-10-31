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
  onAddProducts: () => void;
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

const PRODUCTS_HINT = "Добавить новые товары в каталог, не проводя накладную. Нужны продавец и розничные цены новых товаров";

export default function ActionBar({
  draft,
  dirty,
  busy,
  error,
  onSave,
  onReset,
  onConfirm,
  onDecline,
  onAddProducts,
}: Props) {
  return (
    // above the table, a bar at the bottom would hide behind the on-screen keyboard
    <div className="draft-bar">
      <div className="draft-bar-row">
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
              className="button button-ghost"
              disabled={busy || !draft.products_ready}
              title={PRODUCTS_HINT}
              onClick={onAddProducts}
            >
              Только товары
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
      {/* a touch screen has no tooltip to explain the disabled button */}
      {!dirty && !draft.products_ready && (
        <p className="draft-touch-hint">Для «Только товары» нужны продавец и розничные цены новых товаров</p>
      )}
      {error && <pre className="draft-error">{error}</pre>}
    </div>
  );
}
