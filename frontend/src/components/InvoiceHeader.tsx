import { fromInputDate, toInputDate, toText, type UpdateForm } from "../form";
import type { DraftForm, InvoiceDraft, SupplierSummary } from "../types";
import SupplierPicker from "./SupplierPicker";

interface Props {
  draft: InvoiceDraft;
  form: DraftForm;
  suppliers: SupplierSummary[];
  update: UpdateForm;
  onFound: (supplier: SupplierSummary) => void;
}

export default function InvoiceHeader({ draft, form, suppliers, update, onFound }: Props) {
  return (
    <section className="invoice-head">
      <h1 className="invoice-title">
        <span className="title-word">Накладная</span>
        <input
          className="title-input"
          value={form.invoice_number ?? ""}
          placeholder="номер"
          size={Math.max((form.invoice_number ?? "").length, 5)}
          onChange={(event) =>
            update((current) => ({ ...current, invoice_number: toText(event.target.value) }))
          }
        />
        <span className="title-word">от</span>
        <input
          className={`title-input title-date${form.invoice_date ? "" : " title-date-empty"}`}
          type="date"
          aria-label="Дата накладной"
          value={toInputDate(form.invoice_date)}
          onChange={(event) =>
            update((current) => ({ ...current, invoice_date: fromInputDate(event.target.value) }))
          }
        />
      </h1>
      <SupplierPicker
        key={draft.id}
        draft={draft}
        form={form}
        suppliers={suppliers}
        update={update}
        onFound={onFound}
      />
    </section>
  );
}
