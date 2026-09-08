import { useEffect, useRef, useState } from "react";

import { searchSuppliers } from "../api";
import { formatText } from "../format";
import { toText, type UpdateForm } from "../form";
import type { DraftForm, InvoiceDraft, NewSupplier, SupplierSummary } from "../types";

interface Props {
  draft: InvoiceDraft;
  form: DraftForm;
  suppliers: SupplierSummary[];
  update: UpdateForm;
  // a supplier picked from the search, so the page can show its name
  onFound: (supplier: SupplierSummary) => void;
}

type Mode = "search" | "create";

const SEARCH_DELAY_MS = 250;

export default function SupplierPicker({ draft, form, suppliers, update, onFound }: Props) {
  const chosen = form.supplier;
  const chosenId = chosen !== null && "id" in chosen ? chosen.id : null;
  const isNew = chosen !== null && !("id" in chosen);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>(isNew ? "create" : "search");
  const [search, setSearch] = useState("");
  const [found, setFound] = useState<SupplierSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  // the new supplier fields keep what was typed while an existing one is picked
  const [newSupplier, setNewSupplier] = useState<NewSupplier>(() =>
    chosen !== null && !("id" in chosen)
      ? chosen
      : { name: draft.extraction.supplier.name ?? "", inn: draft.extraction.supplier.inn },
  );

  // the menu closes on a click outside or on escape
  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // an empty query with nothing suggested lists the suppliers from the database
  const needsSearch = open && mode === "search" && (search.trim() !== "" || suppliers.length === 0);

  useEffect(() => {
    if (!needsSearch) {
      setFound(null);
      return;
    }
    // a newer query cancels the answer to an older one
    let current = true;
    setSearching(true);
    setSearchError(null);
    const timer = window.setTimeout(() => {
      searchSuppliers(search)
        .then((result) => current && setFound(result))
        .catch((error) => current && setSearchError(error instanceof Error ? error.message : String(error)))
        .finally(() => current && setSearching(false));
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [needsSearch, search]);

  function pick(supplier: SupplierSummary) {
    onFound(supplier);
    update((current) => ({ ...current, supplier: { id: supplier.id } }));
    setOpen(false);
  }

  function editNew(changes: Partial<NewSupplier>) {
    const next = { ...newSupplier, ...changes };
    setNewSupplier(next);
    if (isNew) {
      update((current) => ({ ...current, supplier: next }));
    }
  }

  function chooseNew() {
    update((current) => ({ ...current, supplier: newSupplier }));
    setOpen(false);
  }

  // nothing found, so what was typed starts the new supplier
  function createFromSearch() {
    const typed = search.trim();
    if (typed) {
      editNew(/^\d+$/.test(typed) ? { inn: typed } : { name: typed });
    }
    setMode("create");
  }

  const picked = suppliers.find((supplier) => supplier.id === chosenId);
  const title = picked?.name ?? (isNew ? newSupplier.name || "Новый продавец" : "Выберите продавца");
  const meta = picked ? `ИНН ${formatText(picked.inn)}` : isNew ? "Новый" : null;
  const results = found ?? (needsSearch ? [] : suppliers);

  return (
    <div className="supplier" ref={root}>
      <button
        type="button"
        className={chosen === null ? "supplier-trigger supplier-empty" : "supplier-trigger"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="supplier-text">
          <span className="supplier-name">{title}</span>
          {meta && <span className="supplier-meta">{meta}</span>}
        </span>
        <svg className="chevron" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>

      {open && (
        <div className="menu">
          <div className="segmented" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "search"}
              className={mode === "search" ? "segment active" : "segment"}
              onClick={() => setMode("search")}
            >
              Найти в базе
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "create"}
              className={mode === "create" ? "segment active" : "segment"}
              onClick={() => setMode("create")}
            >
              Создать нового
            </button>
          </div>

          {mode === "search" ? (
            <>
              <div className="menu-search">
                <input
                  className="input"
                  autoFocus
                  placeholder="Название или ИНН"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                {searching && <span className="spinner menu-spinner" />}
              </div>
              {searchError && <div className="menu-empty menu-error">{searchError}</div>}
              {!search.trim() && found === null && suppliers.length > 0 && (
                <div className="menu-caption">Подходят к этой накладной</div>
              )}
              <div className="menu-results">
                {results.map((supplier) => (
                  <button
                    key={supplier.id}
                    type="button"
                    className={chosenId === supplier.id ? "menu-item selected" : "menu-item"}
                    onClick={() => pick(supplier)}
                  >
                    <span className="menu-title">{supplier.name}</span>
                    <span className="menu-meta">ИНН {formatText(supplier.inn)}</span>
                  </button>
                ))}
              </div>
              {found !== null && found.length === 0 && !searching && (
                <div className="menu-empty">
                  {search.trim() ? "Ничего не нашли." : "В базе пока нет продавцов."}{" "}
                  <button type="button" className="link" onClick={createFromSearch}>
                    Создать нового
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="menu-new">
              <input
                className="input"
                autoFocus
                placeholder="Название"
                value={newSupplier.name}
                onChange={(event) => editNew({ name: event.target.value })}
              />
              <input
                className="input"
                placeholder="ИНН (необязательно)"
                inputMode="numeric"
                value={newSupplier.inn ?? ""}
                onChange={(event) => editNew({ inn: toText(event.target.value.replace(/\D/g, "")) })}
              />
              <button
                type="button"
                className="button button-primary"
                disabled={!newSupplier.name.trim()}
                onClick={chooseNew}
              >
                {isNew ? "Готово" : "Выбрать нового продавца"}
              </button>
              <span className="menu-meta">Продавец появится в базе только после проводки</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
