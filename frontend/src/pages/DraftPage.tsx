import { useEffect, useState, useSyncExternalStore } from "react";

import { addInvoiceProducts, declineInvoice, getDraft, saveForm } from "../api";
import ActionBar from "../components/ActionBar";
import type { Ask } from "../components/ConfirmDialog";
import ConfirmedCard from "../components/ConfirmedCard";
import InvoiceConfirmDialog from "../components/InvoiceConfirmDialog";
import InvoiceHeader from "../components/InvoiceHeader";
import IssuesList from "../components/IssuesList";
import LinesTable from "../components/LinesTable";
import { DraftAutosave } from "../draftAutosave";
import type { UpdateForm } from "../form";
import { message } from "../message";
import { replaceRoute } from "../router";
import type { AddedProducts, ConfirmedInvoice, InvoiceDraft, SupplierSummary } from "../types";

const emptySnapshot = () => null;
const emptySubscribe = () => () => {};

interface Props {
  id: number;
  // the draft just uploaded, so it is not requested again
  initial: InvoiceDraft | null;
  onLoaded: () => void;
  ask: Ask;
  // asked before leaving the page while there are unsaved edits
  setGuard: (guard: (() => Promise<boolean>) | null) => void;
  onHome: () => void;
  onDeclined: (id: number) => void;
  onProductsAdded: (result: AddedProducts) => void;
}

// suppliers seen in any response for this draft, so a choice stays visible after saving it
function mergeSuppliers(known: SupplierSummary[], draft: InvoiceDraft): SupplierSummary[] {
  const merged = new Map(known.map((supplier) => [supplier.id, supplier]));
  for (const supplier of [draft.supplier, ...draft.supplier_candidates]) {
    if (supplier) {
      merged.set(supplier.id, {
        id: supplier.id,
        name: supplier.name,
        short_name: supplier.short_name,
        inn: supplier.inn,
      });
    }
  }
  return [...merged.values()];
}

export default function DraftPage({
  id,
  initial,
  onLoaded,
  ask,
  setGuard,
  onHome,
  onDeclined,
  onProductsAdded,
}: Props) {
  const [editor, setEditor] = useState<DraftAutosave | null>(null);
  const state = useSyncExternalStore(
    editor?.subscribe ?? emptySubscribe,
    editor?.getSnapshot ?? emptySnapshot,
  );
  const draft = state?.draft ?? null;
  const form = state?.form ?? null;
  const [suppliers, setSuppliers] = useState<SupplierSummary[]>([]);
  const [confirmed, setConfirmed] = useState<ConfirmedInvoice | null>(null);
  // the dialog asking the day the goods came
  const [confirming, setConfirming] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dirty = editor?.dirty ?? false;
  const saving = state?.saving ?? false;
  const pending = dirty || saving;

  useEffect(() => {
    let active = true;
    let loadedEditor: DraftAutosave | null = null;
    function loaded(next: InvoiceDraft) {
      if (!active) {
        return;
      }
      loadedEditor = new DraftAutosave({
        draft: next,
        send: (form) => saveForm(next.id, form),
      });
      setEditor(loadedEditor);
      setBusy(false);
      onLoaded();
    }
    if (initial?.id === id) {
      loaded(initial);
    } else {
      setBusy(true);
      getDraft(id)
        .then(loaded)
        .catch((error) => active && setLoadError(message(error)));
    }
    return () => {
      active = false;
      loadedEditor?.stop();
    };
    // the page is keyed by the draft id, the initial draft only matters on mount
  }, []);

  useEffect(() => {
    if (draft) {
      setSuppliers((known) => mergeSuppliers(known, draft));
    }
  }, [draft]);

  useEffect(() => {
    if (!pending || !editor) {
      setGuard(null);
      return;
    }
    setGuard(async () => {
      if (await editor.flush()) {
        return true;
      }
      return ask({
        title: "Не удалось сохранить правки",
        text: "Останьтесь на странице и повторите сохранение. Если уйти, последние правки пропадут.",
        action: "Уйти",
      });
    });
    return () => setGuard(null);
  }, [pending, editor, ask, setGuard]);

  useEffect(() => {
    if (!pending) {
      return;
    }
    function onLeave(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [pending]);

  useEffect(() => {
    function onOnline() {
      void editor?.flush();
    }
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [editor]);

  async function run(action: () => Promise<void>) {
    setActionError(null);
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setActionError(message(error));
    } finally {
      setBusy(false);
    }
  }

  const confirm = (result: ConfirmedInvoice) => {
    setConfirming(false);
    setConfirmed(result);
    // the draft is gone, a reload opens the posted invoice
    replaceRoute({ page: "posted", id: result.id });
  };

  const decline = async () => {
    if (!draft) {
      return;
    }
    const ok = await ask({
      title: `Отклонить черновик №${draft.id}?`,
      text: "Накладная не попадёт в учёт, её можно будет загрузить заново.",
      action: "Отклонить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    void run(async () => {
      await declineInvoice(draft.id);
      onDeclined(draft.id);
    });
  };

  const addProducts = async () => {
    if (!draft) {
      return;
    }
    const ok = await ask({
      title: "Добавить только товары?",
      text: "Новые товары появятся в каталоге. Накладная не попадёт в учёт и историю, цены товаров из каталога не изменятся.",
      action: "Добавить",
    });
    if (!ok) {
      return;
    }
    void run(async () => {
      onProductsAdded(await addInvoiceProducts(draft.id));
    });
  };

  const update: UpdateForm = (change) => {
    setActionError(null);
    editor?.update(change);
  };

  if (confirmed) {
    return (
      <main className="page page-empty">
        <ConfirmedCard result={confirmed} onHome={onHome} />
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="page page-empty">
        <h1 className="hero-title">Черновик не открылся</h1>
        <div className="alert">
          <pre>{loadError}</pre>
        </div>
        <button type="button" className="button button-ghost back-button" onClick={onHome}>
          К накладным
        </button>
      </main>
    );
  }

  if (!draft || !form) {
    return (
      <main className="page page-empty">
        <span className="spinner page-spinner" />
      </main>
    );
  }

  return (
    <main className="page">
      <InvoiceHeader
        draft={draft}
        form={form}
        suppliers={suppliers}
        update={update}
        onFound={(supplier) =>
          setSuppliers((known) =>
            known.some((item) => item.id === supplier.id) ? known : [...known, supplier],
          )
        }
        onHome={onHome}
      />
      <ActionBar
        draft={draft}
        dirty={dirty}
        saving={saving}
        saved={state?.saved ?? false}
        busy={busy}
        error={state?.error ?? actionError}
        onSave={() => void editor?.flush()}
        onReset={() => editor?.reset()}
        onConfirm={() => setConfirming(true)}
        onDecline={decline}
        onAddProducts={addProducts}
      />
      <IssuesList issues={draft.issues.filter((issue) => issue.line === null)} stale={dirty} />
      <LinesTable draft={draft} form={form} dirty={dirty} update={update} />
      {confirming && (
        <InvoiceConfirmDialog
          invoiceId={draft.id}
          invoiceDate={draft.form.invoice_date}
          onClose={() => setConfirming(false)}
          onConfirmed={confirm}
        />
      )}
    </main>
  );
}
