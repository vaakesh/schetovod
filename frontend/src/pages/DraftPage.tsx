import { useEffect, useState } from "react";

import { declineInvoice, getDraft, saveForm } from "../api";
import ActionBar from "../components/ActionBar";
import type { Ask } from "../components/ConfirmDialog";
import ConfirmedCard from "../components/ConfirmedCard";
import InvoiceConfirmDialog from "../components/InvoiceConfirmDialog";
import InvoiceHeader from "../components/InvoiceHeader";
import IssuesList from "../components/IssuesList";
import LinesTable from "../components/LinesTable";
import type { UpdateForm } from "../form";
import { message } from "../message";
import { replaceRoute } from "../router";
import type { ConfirmedInvoice, DraftForm, InvoiceDraft, SupplierSummary } from "../types";

interface Props {
  id: number;
  // the draft just uploaded, so it is not requested again
  initial: InvoiceDraft | null;
  ask: Ask;
  // asked before leaving the page while there are unsaved edits
  setGuard: (guard: (() => Promise<boolean>) | null) => void;
  onHome: () => void;
  onDeclined: (id: number) => void;
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

export default function DraftPage({ id, initial, ask, setGuard, onHome, onDeclined }: Props) {
  const [draft, setDraft] = useState<InvoiceDraft | null>(null);
  const [form, setForm] = useState<DraftForm | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierSummary[]>([]);
  const [confirmed, setConfirmed] = useState<ConfirmedInvoice | null>(null);
  // the dialog asking the day the goods came
  const [confirming, setConfirming] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dirty = draft !== null && JSON.stringify(form) !== JSON.stringify(draft.form);

  function show(next: InvoiceDraft, fresh: boolean) {
    setDraft(next);
    setForm(next.form);
    setSuppliers((known) => mergeSuppliers(fresh ? [] : known, next));
    setActionError(null);
  }

  useEffect(() => {
    if (initial?.id === id) {
      show(initial, true);
      return;
    }
    setBusy(true);
    getDraft(id)
      .then((loaded) => show(loaded, true))
      .catch((error) => setLoadError(message(error)))
      .finally(() => setBusy(false));
    // the page is keyed by the draft id, the initial draft only matters on mount
  }, []);

  useEffect(() => {
    if (!dirty) {
      setGuard(null);
      return;
    }
    setGuard(() =>
      ask({
        title: "Уйти со страницы?",
        text: "Несохранённые правки пропадут. Сохранённый черновик останется в списке накладных.",
        action: "Уйти",
      }),
    );
    return () => setGuard(null);
  }, [dirty, ask, setGuard]);

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

  const save = () =>
    run(async () => {
      if (draft && form) {
        show(await saveForm(draft.id, form), false);
      }
    });

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

  const update: UpdateForm = (change) => setForm((current) => (current ? change(current) : current));

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
      />
      <IssuesList issues={draft.issues.filter((issue) => issue.line === null)} stale={dirty} />
      <LinesTable draft={draft} form={form} dirty={dirty} update={update} />
      <ActionBar
        draft={draft}
        dirty={dirty}
        busy={busy}
        error={actionError}
        onSave={save}
        onReset={() => setForm(draft.form)}
        onConfirm={() => setConfirming(true)}
        onDecline={decline}
      />
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
