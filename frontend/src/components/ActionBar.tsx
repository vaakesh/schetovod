import type { InvoiceDraft } from "../types";

interface Props {
  draft: InvoiceDraft;
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  busy: boolean;
  error: string | null;
  onSave: () => void;
  onReset: () => void;
  onConfirm: () => void;
  onDecline: () => void;
  onAddProducts: () => void;
}

function hint(
  draft: InvoiceDraft,
  dirty: boolean,
  saving: boolean,
  saved: boolean,
  error: string | null,
): string {
  if (saving) {
    return "Сохраняем…";
  }
  if (dirty) {
    return error ? "Правки не сохранены" : "Сохранится автоматически";
  }
  const blocking = draft.issues.filter((issue) => issue.blocking).length;
  if (blocking > 0) {
    return `${saved ? "Сохранено · " : ""}Осталось исправить: ${blocking}`;
  }
  return `${saved ? "Сохранено · " : ""}Всё сходится`;
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
  saving,
  saved,
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
        <span className={tone(draft, dirty)} role="status">
          {hint(draft, dirty, saving, saved, error)}
        </span>
        {dirty ? (
          <>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy || saving}
              onClick={onReset}
            >
              Отменить
            </button>
            <button
              type="button"
              className="button button-primary"
              disabled={busy || saving}
              onClick={onSave}
            >
              {error ? "Повторить сохранение" : "Сохранить сейчас"}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy || saving}
              onClick={onDecline}
            >
              Отклонить
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy || saving || !draft.products_ready}
              title={PRODUCTS_HINT}
              onClick={onAddProducts}
            >
              Только товары
            </button>
            <button
              type="button"
              className="button button-primary"
              disabled={busy || saving || !draft.ready}
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
