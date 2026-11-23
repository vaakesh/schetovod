import { memo, useMemo, useRef, useState, type ReactNode } from "react";

import { formatMoney } from "../format";
import { nameKey, stocktakeQuantity, type CountLine } from "../stocktakes";
import Icon from "./icons";
import PurchaseMenu from "./PurchaseMenu";

const sortGroups = [
  { label: "Порядок ввода", options: [["entered", "С начала"], ["newest", "С конца"]] },
  { label: "Название", options: [["nameAsc", "От А до Я"], ["nameDesc", "От Я до А"]] },
  { label: "Цена за единицу", options: [["priceAsc", "От низкой"], ["priceDesc", "От высокой"]] },
] as const;
type SortOrder = (typeof sortGroups)[number]["options"][number][0];

const sortTitles: Record<SortOrder, string> = {
  entered: "В порядке ввода",
  newest: "Сначала последние",
  nameAsc: "От А до Я",
  nameDesc: "От Я до А",
  priceAsc: "Сначала дешевле",
  priceDesc: "Сначала дороже",
};

const storageKey = "gastronom:stocktake:sort";
const byName = new Intl.Collator("ru", { sensitivity: "base", numeric: true, ignorePunctuation: true });

function savedOrder(): SortOrder {
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved && Object.hasOwn(sortTitles, saved)) return saved as SortOrder;
  } catch {
    // use entry order when storage is unavailable
  }
  return "entered";
}

function compareLines(a: CountLine, b: CountLine, order: SortOrder): number {
  const entered = a.id - b.id;
  switch (order) {
    case "entered": return entered;
    case "newest": return -entered;
    case "nameAsc": return byName.compare(a.name, b.name) || entered;
    case "nameDesc": return byName.compare(b.name, a.name) || entered;
    case "priceAsc":
    case "priceDesc": {
      if (a.price === null || b.price === null) {
        return Number(a.price === null) - Number(b.price === null) || entered;
      }
      const difference = Number(a.price) - Number(b.price);
      return (order === "priceAsc" ? difference : -difference) || entered;
    }
  }
}

interface Props {
  lines: CountLine[];
  total: string;
  query: string;
  onQueryChange: (value: string) => void;
  editable: boolean;
  busy: boolean;
  highlight: number | null;
  edit: (line: CountLine) => void;
  remove: (line: CountLine) => void;
  feedback: ReactNode;
}

function StocktakeLines({ lines, total, query, onQueryChange, editable, busy, highlight, edit, remove, feedback }: Props) {
  const [order, setOrder] = useState(savedOrder);
  const searchInput = useRef<HTMLInputElement>(null);
  const search = nameKey(query);
  const sorted = useMemo(
    () => [...lines].sort((a, b) => compareLines(a, b, order)),
    [lines, order],
  );
  const visible = useMemo(() => {
    if (!search) return sorted;
    const terms = search.split(" ");
    return sorted.filter(({ name }) => {
      const text = nameKey(name);
      return terms.every((term) => text.includes(term));
    });
  }, [sorted, search]);

  function clearSearch() {
    onQueryChange("");
    searchInput.current?.focus();
  }

  function changeOrder(value: SortOrder) {
    setOrder(value);
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // keep the selection for the current view
    }
  }

  return (
    <section>
      <div className="count-summary">
        <h2 className="section-title" id="stocktake-positions" tabIndex={-1}>Позиции{" "}
          <span role="status">{search ? `${visible.length} из ${lines.length}` : lines.length}</span>
        </h2>
        <div className="count-total"><span>Итого по переучёту</span><strong>{formatMoney(total)} ₽</strong></div>
      </div>
      {feedback}
      <div className="sheet count-list">
        {lines.length > 0 && (
          <div className="count-list-tools">
            <div className="count-search">
              <Icon name="search" size={17} />
              <input
                ref={searchInput}
                type="search"
                className="input"
                aria-label="Поиск позиций в переучёте"
                placeholder="Найти позицию"
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape" && query) {
                    event.preventDefault();
                    clearSearch();
                  }
                }}
              />
              {query && (
                <button className="count-search-clear" type="button" aria-label="Очистить поиск" onClick={clearSearch}>
                  <Icon name="close" size={15} />
                </button>
              )}
            </div>
            {lines.length > 1 && (
              <div className="purchase-sort count-sort">
                <PurchaseMenu
                  label="Сортировка позиций"
                  icon="sort"
                  value={order}
                  title={sortTitles[order]}
                  groups={sortGroups}
                  onChange={changeOrder}
                />
              </div>
            )}
          </div>
        )}
        {lines.length === 0 ? (
          <p className="list-empty">В переучёте пока нет позиций</p>
        ) : visible.length === 0 ? (
          <div className="list-empty count-search-empty">
            <p>Позиции не найдены</p>
            <button type="button" className="button button-soft" onClick={clearSearch}>Сбросить поиск</button>
          </div>
        ) : (
          <table className="list count-table">
            <thead>
              <tr>
                <th aria-sort={order === "nameAsc" ? "ascending" : order === "nameDesc" ? "descending" : undefined}>
                  Товар
                </th>
                <th className="num" aria-sort={order === "priceAsc" ? "ascending" : order === "priceDesc" ? "descending" : undefined}>
                  Цена, ₽
                </th>
                <th className="num">Остаток</th>
                <th className="num">Сумма, ₽</th>
                {editable && <th className="count-row-action" aria-label="Действия" />}
              </tr>
            </thead>
            <tbody>
              {visible.map((line) => (
                <tr
                  key={line.id}
                  tabIndex={-1}
                  id={`count-line-${line.id}`}
                  className={line.id === highlight ? "count-highlight" : ""}
                >
                  <th scope="row">
                    {editable ? (
                      <button
                        className="count-edit"
                        type="button"
                        disabled={busy}
                        onClick={() => edit(line)}
                        title="Изменить строку"
                      >
                        {line.name}
                      </button>
                    ) : (
                      line.name
                    )}
                  </th>
                  <td className="num" data-label="Цена">
                    {formatMoney(line.price)} {line.price !== null && <span className="count-mobile">₽</span>}
                  </td>
                  <td className="num" data-label="Остаток">
                    {stocktakeQuantity(line) ?? "По сумме"}
                  </td>
                  <td className="num strong" data-label="Сумма">
                    {formatMoney(line.amount)} <span className="count-mobile">₽</span>
                  </td>
                  {editable && (
                    <td className="count-row-action">
                      <button
                        type="button"
                        className="row-delete"
                        aria-label={`Удалить позицию «${line.name}»`}
                        title="Удалить позицию"
                        disabled={busy}
                        onClick={() => remove(line)}
                      >
                        <Icon name="close" size={16} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

export default memo(StocktakeLines);
