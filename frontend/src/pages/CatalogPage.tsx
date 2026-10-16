import { useEffect, useMemo, useState } from "react";

import { getCatalog } from "../api";
import ProductEditDialog from "../components/ProductEditDialog";
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
  | "retail_price";

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
];

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

function percent(value: string | null): string {
  return value === null ? formatText(null) : `${formatNumber(value)}%`;
}

function ProductRows({
  products,
  suppliers,
  sort,
  onSort,
  onEdit,
}: {
  products: CatalogProduct[];
  // the supplier column is shown only in the list of all products
  suppliers?: Map<number, SupplierSummary>;
  sort: Sort;
  onSort: (field: SortField) => void;
  onEdit: (product: CatalogProduct) => void;
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
                {product.spellings.length > 0 && (
                  <span className="catalog-spellings">также: {product.spellings.join(", ")}</span>
                )}
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CatalogPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>(savedView);
  const [sort, setSort] = useState<Sort>(savedSort);
  const [open, setOpen] = useState<Set<number>>(() => new Set());
  const [editing, setEditing] = useState<CatalogProduct | null>(null);
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

  const key = normalize(search);

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
      .filter(
        (product) =>
          !key ||
          normalize(product.name).includes(key) ||
          product.spellings.some((spelling) => normalize(spelling).includes(key)),
      )
      .sort((a, b) => compare(a, b, sort, suppliers));
  }, [catalog, key, sort, suppliers]);

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
    setOpen((previous) => {
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

  // a search shows only the suppliers with matches, already opened
  const shownSuppliers = (catalog?.suppliers ?? []).filter(
    (supplier) => !key || bySupplier.has(supplier.id),
  );

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
        <input
          className="input search"
          type="search"
          placeholder="Поиск по всем товарам"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
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
                sort={sort}
                onSort={changeSort}
                onEdit={setEditing}
              />
            ) : (
              <p className="list-empty">{key ? "Ничего не найдено" : "Товаров пока нет"}</p>
            )}
          </section>
        ) : shownSuppliers.length > 0 ? (
          <div className="catalog-groups">
            {shownSuppliers.map((supplier) => {
              const products = bySupplier.get(supplier.id) ?? [];
              const expanded = key !== "" || open.has(supplier.id);
              return (
                <section key={supplier.id} className="sheet catalog-group">
                  <button
                    type="button"
                    className="catalog-supplier"
                    aria-expanded={expanded}
                    disabled={key !== ""}
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
                      <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" />
                    </svg>
                    <span className="catalog-supplier-name">{supplier.name}</span>
                    {supplier.inn && <span className="supplier-meta">ИНН {supplier.inn}</span>}
                    <span className="catalog-count">{products.length}</span>
                  </button>
                  {expanded &&
                    (products.length > 0 ? (
                      <ProductRows
                        products={products}
                        sort={sort}
                        onSort={changeSort}
                        onEdit={setEditing}
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
    </main>
  );
}
