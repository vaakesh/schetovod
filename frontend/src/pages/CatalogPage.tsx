import { useEffect, useMemo, useState } from "react";

import { getCatalog, markPriceTag } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import ProductEditDialog from "../components/ProductEditDialog";
import SupplierEditDialog from "../components/SupplierEditDialog";
import { formatMoney, formatNumber, formatSigned, formatText } from "../format";
import { message } from "../message";
import type { Catalog, CatalogProduct, LedgerPosted, SupplierSummary } from "../types";

type View = "suppliers" | "alphabet";

const VIEWS: { view: View; label: string }[] = [
  { view: "suppliers", label: "По поставщикам" },
  { view: "alphabet", label: "По алфавиту" },
];

const VIEW_KEY = "catalog-view";
const SORT_KEY = "catalog-sort";

type SortField =
  | "name"
  | "supplier"
  | "unit"
  | "cost_price"
  | "vat_percent"
  | "markup_pct"
  | "retail_price"
  | "has_price_tag";

interface Sort {
  field: SortField;
  desc: boolean;
}

const DEFAULT_SORT: Sort = { field: "name", desc: false };

const COLUMNS: { field: SortField; label: string; num?: boolean }[] = [
  { field: "name", label: "Название" },
  { field: "supplier", label: "Поставщик" },
  { field: "unit", label: "Ед." },
  { field: "cost_price", label: "Закупка", num: true },
  { field: "vat_percent", label: "НДС", num: true },
  { field: "markup_pct", label: "Наценка", num: true },
  { field: "retail_price", label: "Розница", num: true },
  { field: "has_price_tag", label: "Ценник" },
];

type Filter = "all" | "untagged";

const FILTER_KEY = "catalog-filter";

// the same key as normalize_name on the backend, so a spelling is found however it is typed
function normalize(name: string): string {
  return name
    .toLowerCase()
    .replaceAll("ё", "е")
    .replace(/["'«»“”„`]/g, " ")
    .replace(/\s*([.,;:()/%-])\s*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function byName(a: CatalogProduct, b: CatalogProduct): number {
  return a.name.localeCompare(b.name, "ru") || a.id - b.id;
}

function sortValue(
  product: CatalogProduct,
  field: SortField,
  suppliers: Map<number, SupplierSummary>,
): string | number | null {
  switch (field) {
    case "name":
      return product.name;
    case "supplier":
      return suppliers.get(product.supplier_id)?.name ?? null;
    case "unit":
      return product.unit;
    // ascending starts with the products whose tag is missing
    case "has_price_tag":
      return product.has_price_tag ? 1 : 0;
    default:
      return product[field] === null ? null : Number(product[field]);
  }
}

// an empty value goes last in both directions, equal values keep the name order
function compare(
  a: CatalogProduct,
  b: CatalogProduct,
  sort: Sort,
  suppliers: Map<number, SupplierSummary>,
): number {
  const left = sortValue(a, sort.field, suppliers);
  const right = sortValue(b, sort.field, suppliers);
  if (left === null || right === null) {
    return left === right ? byName(a, b) : left === null ? 1 : -1;
  }
  const order =
    typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), "ru");
  return (sort.desc ? -order : order) || byName(a, b);
}

function savedSort(): Sort {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(SORT_KEY) ?? "null");
    if (
      typeof saved === "object" &&
      saved !== null &&
      "field" in saved &&
      "desc" in saved &&
      COLUMNS.some((column) => column.field === saved.field)
    ) {
      return { field: saved.field as SortField, desc: saved.desc === true };
    }
  } catch {
    // a broken or unavailable storage falls back to the name order
  }
  return DEFAULT_SORT;
}

function saveSort(sort: Sort) {
  try {
    window.localStorage.setItem(SORT_KEY, JSON.stringify(sort));
  } catch {
    // nothing to do, the order is kept until the page is left
  }
}

// the storage may be unavailable, the view then is not remembered
function savedView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "alphabet" ? "alphabet" : "suppliers";
  } catch {
    return "suppliers";
  }
}

function saveView(view: View) {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // nothing to do, the view is kept until the page is left
  }
}

function savedFilter(): Filter {
  try {
    return window.localStorage.getItem(FILTER_KEY) === "untagged" ? "untagged" : "all";
  } catch {
    return "all";
  }
}

function saveFilter(filter: Filter) {
  try {
    window.localStorage.setItem(FILTER_KEY, filter);
  } catch {
    // nothing to do, the filter is kept until the page is left
  }
}

const SPELLINGS_KEY = "catalog-spellings";

// hidden unless asked for, they take a lot of room
function savedSpellings(): boolean {
  try {
    return window.localStorage.getItem(SPELLINGS_KEY) === "shown";
  } catch {
    return false;
  }
}

function saveSpellings(shown: boolean) {
  try {
    window.localStorage.setItem(SPELLINGS_KEY, shown ? "shown" : "hidden");
  } catch {
    // nothing to do, the choice is kept until the page is left
  }
}

function percent(value: string | null): string {
  return value === null ? formatText(null) : `${formatNumber(value)}%`;
}

// a few spellings are enough to recognize the product, the rest wait for a click
const SPELLINGS_SHOWN = 2;

function Spellings({
  name,
  spellings,
  shown: all,
  searchKey,
}: {
  name: string;
  spellings: string[];
  // the toggle above the list
  shown: boolean;
  searchKey: string;
}) {
  const [open, setOpen] = useState(false);
  if (spellings.length === 0) {
    return null;
  }
  // a product found by another spelling tells which one, the toggle aside
  if (!all) {
    if (!searchKey || normalize(name).includes(searchKey)) {
      return null;
    }
    const matched = spellings.filter((spelling) => normalize(spelling).includes(searchKey));
    return <span className="catalog-spellings">найдено как: {matched.join(", ")}</span>;
  }
  const hidden = spellings.length - SPELLINGS_SHOWN;
  const shown = open || hidden <= 0 ? spellings : spellings.slice(0, SPELLINGS_SHOWN);
  return (
    <span className="catalog-spellings">
      <span className="catalog-spellings-label">также:</span>
      {shown.map((spelling) => (
        <span key={spelling} className="catalog-spelling">
          {spelling}
        </span>
      ))}
      {hidden > 0 && (
        <button
          type="button"
          className="catalog-spellings-more"
          // the row opens the product editor, the button only unfolds the list
          onClick={(event) => {
            event.stopPropagation();
            setOpen(!open);
          }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {open ? "свернуть" : `показать ещё ${hidden}`}
        </button>
      )}
    </span>
  );
}

function ProductRows({
  products,
  suppliers,
  spellings,
  searchKey,
  sort,
  tagging,
  onSort,
  onEdit,
  onTag,
}: {
  products: CatalogProduct[];
  // the supplier column is shown only in the list of all products
  suppliers?: Map<number, SupplierSummary>;
  spellings: boolean;
  searchKey: string;
  sort: Sort;
  tagging: number | null;
  onSort: (field: SortField) => void;
  onEdit: (product: CatalogProduct) => void;
  onTag: (product: CatalogProduct) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="list catalog-table">
        <thead>
          <tr>
            {COLUMNS.filter((column) => suppliers || column.field !== "supplier").map((column) => {
              const active = sort.field === column.field;
              return (
                <th
                  key={column.field}
                  className={column.num ? "num" : undefined}
                  aria-sort={active ? (sort.desc ? "descending" : "ascending") : undefined}
                >
                  <button
                    type="button"
                    className={active ? "sort-button active" : "sort-button"}
                    onClick={() => onSort(column.field)}
                  >
                    {column.label}
                    <span className="sort-arrow" aria-hidden="true">
                      {active ? (sort.desc ? "↓" : "↑") : ""}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <tr
              key={product.id}
              className="list-row clickable"
              tabIndex={0}
              title="Исправить название или цену"
              onClick={() => onEdit(product)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  onEdit(product);
                }
              }}
            >
              <td className="catalog-name">
                <span className="catalog-product">{product.name}</span>
                <Spellings
                  name={product.name}
                  spellings={product.spellings}
                  shown={spellings}
                  searchKey={searchKey}
                />
              </td>
              {suppliers && (
                <td className="muted-cell">
                  {formatText(suppliers.get(product.supplier_id)?.name ?? null)}
                </td>
              )}
              <td className="nowrap muted-cell">{formatText(product.unit)}</td>
              <td className="num">{formatMoney(product.cost_price)}</td>
              <td className="num muted-cell">{percent(product.vat_percent)}</td>
              <td className="num muted-cell">{percent(product.markup_pct)}</td>
              <td className="num strong">
                {product.retail_price === null
                  ? formatText(null)
                  : `${formatMoney(product.retail_price)} ₽`}
              </td>
              {/* the checkbox asks first, a click or a key on it does not open the edit */}
              <td
                className="catalog-tag"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                <input
                  type="checkbox"
                  className="catalog-tag-box"
                  aria-label={`Ценник висит: ${product.name}`}
                  checked={product.has_price_tag}
                  disabled={tagging === product.id}
                  onChange={() => onTag(product)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  ask: Ask;
}

export default function CatalogPage({ ask }: Props) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>(savedView);
  const [sort, setSort] = useState<Sort>(savedSort);
  const [filter, setFilter] = useState<Filter>(savedFilter);
  const [spellings, setSpellings] = useState(savedSpellings);
  // the product whose tag is being saved, its checkbox waits for the answer
  const [tagging, setTagging] = useState<number | null>(null);
  const [open, setOpen] = useState<Set<number>>(() => new Set());
  // a search or the filter opens every supplier, these were closed by hand since then
  const [closed, setClosed] = useState<Set<number>>(() => new Set());
  const [editing, setEditing] = useState<CatalogProduct | null>(null);
  const [editingSupplier, setEditingSupplier] = useState<SupplierSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // bumped after an edit to load the catalog again
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    getCatalog()
      .then((next) => {
        if (current) {
          setCatalog(next);
          setError(null);
        }
      })
      .catch((reason) => current && setError(message(reason)));
    return () => {
      current = false;
    };
  }, [version]);

  function saved(posted: LedgerPosted | null) {
    setEditing(null);
    setNotice(
      posted
        ? `Товар сохранён, переоценка ${formatSigned(posted.amount)} ₽ записана в журнал`
        : "Товар сохранён",
    );
    setVersion((previous) => previous + 1);
  }

  // a misclick must not mark a tag, both directions ask first
  async function tag(product: CatalogProduct) {
    if (tagging !== null) {
      return;
    }
    const price = `${formatMoney(product.retail_price)} ₽`;
    const ok = await ask(
      product.has_price_tag
        ? {
            title: "Снять отметку о ценнике?",
            text: `«${product.name}» окажется в списке без ценника.`,
            action: "Снять",
            danger: true,
          }
        : {
            title: "Ценник висит?",
            text: `На полке ценник «${product.name}» с ценой ${price}.`,
            action: "Висит",
          },
    );
    if (!ok) {
      return;
    }
    setTagging(product.id);
    setNotice(null);
    try {
      await markPriceTag(product.id, !product.has_price_tag, Number(product.retail_price));
      setError(null);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setTagging(null);
      setVersion((previous) => previous + 1);
    }
  }

  // a new search or filter opens every supplier with matches again
  function changeFilter(next: Filter) {
    setFilter(next);
    saveFilter(next);
    setClosed(new Set());
  }

  function changeSearch(next: string) {
    setSearch(next);
    setClosed(new Set());
  }

  function toggleSpellings() {
    setSpellings(!spellings);
    saveSpellings(!spellings);
  }

  const key = normalize(search);
  // a search or the filter narrows the list, the suppliers with matches open by themselves
  const narrowed = key !== "" || filter === "untagged";
  const untagged = catalog?.products.filter((product) => !product.has_price_tag).length ?? 0;

  const suppliers = useMemo(
    () => new Map(catalog?.suppliers.map((supplier) => [supplier.id, supplier])),
    [catalog],
  );

  // the whole catalog is here, the search and the order work without asking the backend
  const found = useMemo(() => {
    if (!catalog) {
      return [];
    }
    return catalog.products
      .filter((product) => filter === "all" || !product.has_price_tag)
      .filter(
        (product) =>
          !key ||
          normalize(product.name).includes(key) ||
          product.spellings.some((spelling) => normalize(spelling).includes(key)),
      )
      .sort((a, b) => compare(a, b, sort, suppliers));
  }, [catalog, key, filter, sort, suppliers]);

  // the same column again turns the order around, another one starts ascending
  function changeSort(field: SortField) {
    const next = { field, desc: sort.field === field && !sort.desc };
    setSort(next);
    saveSort(next);
  }

  const bySupplier = useMemo(() => {
    const groups = new Map<number, CatalogProduct[]>();
    for (const product of found) {
      const group = groups.get(product.supplier_id);
      if (group) {
        group.push(product);
      } else {
        groups.set(product.supplier_id, [product]);
      }
    }
    return groups;
  }, [found]);

  function changeView(next: View) {
    setView(next);
    saveView(next);
  }

  function toggle(id: number) {
    (narrowed ? setClosed : setOpen)((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) {
        next.add(id);
      }
      return next;
    });
  }

  if (catalog !== null && catalog.suppliers.length === 0) {
    return (
      <main className="page page-empty">
        <h1 className="hero-title">Товаров пока нет</h1>
        <p className="catalog-hint">Они появятся здесь после первой проведённой накладной</p>
      </main>
    );
  }

  const shownSuppliers = (catalog?.suppliers ?? []).filter(
    (supplier) => !narrowed || bySupplier.has(supplier.id),
  );
  const empty = key ? "Ничего не найдено" : narrowed ? "Все ценники висят" : "Товаров пока нет";

  return (
    <main className="page">
      {notice && <p className="page-notice">{notice}</p>}
      <div className="list-head">
        <div className="segments" role="tablist">
          {VIEWS.map((item) => (
            <button
              key={item.view}
              type="button"
              role="tab"
              aria-selected={view === item.view}
              className={view === item.view ? "segment active" : "segment"}
              onClick={() => changeView(item.view)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="segments" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={filter === "all"}
            className={filter === "all" ? "segment active" : "segment"}
            onClick={() => changeFilter("all")}
          >
            Все
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === "untagged"}
            className={filter === "untagged" ? "segment active" : "segment"}
            onClick={() => changeFilter("untagged")}
          >
            Без ценника · {untagged}
          </button>
        </div>
        <div className="segments">
          <button
            type="button"
            aria-pressed={spellings}
            className={spellings ? "segment active" : "segment"}
            title="Как товар назывался в других накладных"
            onClick={toggleSpellings}
          >
            Другие названия
          </button>
        </div>
        <input
          className="input search"
          type="search"
          placeholder="Поиск по всем товарам"
          value={search}
          onChange={(event) => changeSearch(event.target.value)}
        />
      </div>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      {catalog &&
        (view === "alphabet" ? (
          <section className="sheet">
            {found.length > 0 ? (
              <ProductRows
                products={found}
                suppliers={suppliers}
                spellings={spellings}
                searchKey={key}
                sort={sort}
                tagging={tagging}
                onSort={changeSort}
                onEdit={setEditing}
                onTag={(product) => void tag(product)}
              />
            ) : (
              <p className="list-empty">{empty}</p>
            )}
          </section>
        ) : shownSuppliers.length > 0 ? (
          <div className="catalog-groups">
            {shownSuppliers.map((supplier) => {
              const products = bySupplier.get(supplier.id) ?? [];
              const expanded = narrowed ? !closed.has(supplier.id) : open.has(supplier.id);
              return (
                <section key={supplier.id} className="sheet catalog-group">
                  <div className="catalog-supplier-row">
                    <button
                      type="button"
                      className="catalog-supplier"
                      aria-expanded={expanded}
                      onClick={() => toggle(supplier.id)}
                    >
                      <svg
                        className={
                          expanded ? "chevron catalog-chevron open" : "chevron catalog-chevron"
                        }
                        width="16"
                        height="16"
                        viewBox="0 0 16 16"
                        aria-hidden="true"
                      >
                        <path
                          d="M6 4l4 4-4 4"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        />
                      </svg>
                      <span className="catalog-supplier-name">{supplier.name}</span>
                      {supplier.inn && <span className="supplier-meta">ИНН {supplier.inn}</span>}
                      {supplier.short_name && (
                        <span className="supplier-meta">в отчётах: {supplier.short_name}</span>
                      )}
                      <span className="catalog-count">{products.length}</span>
                    </button>
                    <button
                      type="button"
                      className="catalog-supplier-edit"
                      aria-label="Изменить поставщика"
                      title="Короткое имя для отчётов"
                      onClick={() => setEditingSupplier(supplier)}
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                        <path
                          d="M10.5 2.5l3 3L5 14H2v-3z"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                  {expanded &&
                    (products.length > 0 ? (
                      <ProductRows
                        products={products}
                        spellings={spellings}
                        searchKey={key}
                        sort={sort}
                        tagging={tagging}
                        onSort={changeSort}
                        onEdit={setEditing}
                        onTag={(product) => void tag(product)}
                      />
                    ) : (
                      <p className="list-empty">Товаров пока нет</p>
                    ))}
                </section>
              );
            })}
          </div>
        ) : (
          <section className="sheet">
            <p className="list-empty">Ничего не найдено</p>
          </section>
        ))}

      {editing && (
        <ProductEditDialog
          key={editing.id}
          product={editing}
          onClose={() => setEditing(null)}
          onSaved={saved}
        />
      )}
      {editingSupplier && (
        <SupplierEditDialog
          key={editingSupplier.id}
          supplier={editingSupplier}
          onClose={() => setEditingSupplier(null)}
          onSaved={() => {
            setEditingSupplier(null);
            setNotice("Поставщик сохранён");
            setVersion((previous) => previous + 1);
          }}
        />
      )}
    </main>
  );
}
