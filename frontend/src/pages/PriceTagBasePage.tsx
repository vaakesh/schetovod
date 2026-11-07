import { useEffect, useMemo, useState } from "react";

import { deletePriceTag, getAllPriceTags } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import PageHead from "../components/PageHead";
import PriceTagDialog from "../components/PriceTagDialog";
import PriceTagTabs from "../components/PriceTagTabs";
import SlidingThumb from "../components/SlidingThumb";
import { formatDateTime, formatMoney, plural } from "../format";
import { message } from "../message";
import { ORIGIN_LABELS, SIZES, UNIT_LABELS, addToForm, sizeLabel, type SizeKey } from "../priceTags";
import type { Route } from "../router";
import type { PriceTag } from "../types";

type SortField = "name" | "price" | "created_at";

interface Sort {
  field: SortField;
  desc: boolean;
}

const COLUMNS: { field: SortField; label: string; num?: boolean }[] = [
  { field: "name", label: "Название" },
  { field: "price", label: "Цена", num: true },
  { field: "created_at", label: "Добавлен" },
];

// case, ё and the no-break spaces of the print do not matter for a search
function normalize(text: string): string {
  return text.toLowerCase().replaceAll("ё", "е").replace(/\s+/g, " ").trim();
}

function searchText(tag: PriceTag): string {
  return normalize([tag.name, tag.subtitle ?? "", tag.pack ?? "", tag.origin_name].join(" "));
}

function compare(a: PriceTag, b: PriceTag, sort: Sort): number {
  let order = 0;
  if (sort.field === "price") {
    // a tag without a price goes last either way
    if (a.price === null || b.price === null) {
      return a.price === b.price ? a.name.localeCompare(b.name, "ru") : a.price === null ? 1 : -1;
    }
    order = Number(a.price) - Number(b.price);
  } else if (sort.field === "created_at") {
    order = a.created_at.localeCompare(b.created_at);
  } else {
    order = a.name.localeCompare(b.name, "ru");
  }
  order = order || (a.subtitle ?? "").localeCompare(b.subtitle ?? "", "ru") || a.id - b.id;
  return sort.desc ? -order : order;
}

interface Props {
  ask: Ask;
  go: (route: Route) => void;
}

export default function PriceTagBasePage({ ask, go }: Props) {
  const [tags, setTags] = useState<PriceTag[] | null>(null);
  const [search, setSearch] = useState("");
  const [size, setSize] = useState<SizeKey | "all">("all");
  const [sort, setSort] = useState<Sort>({ field: "name", desc: false });
  // kept across the search and the filter, tags may be gathered from several lists
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<PriceTag | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    getAllPriceTags()
      .then(setTags)
      .catch((reason) => setError(message(reason)));
  }, []);

  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const tag of tags ?? []) {
      const key = `${tag.width_mm}x${tag.height_mm}`;
      result.set(key, (result.get(key) ?? 0) + 1);
    }
    return result;
  }, [tags]);

  // the whole base is here, the search and the order work without asking the backend
  const found = useMemo(() => {
    const words = normalize(search).split(" ").filter(Boolean);
    return (tags ?? [])
      .filter((tag) => size === "all" || `${tag.width_mm}x${tag.height_mm}` === size)
      .filter((tag) => {
        const text = searchText(tag);
        return words.every((word) => text.includes(word));
      })
      .sort((a, b) => compare(a, b, sort));
  }, [tags, size, sort, search]);

  const allPicked = found.length > 0 && found.every((tag) => picked.has(tag.id));
  const pickedTags = (tags ?? []).filter((tag) => picked.has(tag.id));

  function changeSort(field: SortField) {
    // the newest first is what one looks for in the dates
    setSort((current) =>
      current.field === field
        ? { field, desc: !current.desc }
        : { field, desc: field === "created_at" },
    );
  }

  function toggle(id: number) {
    setPicked((current) => {
      const next = new Set(current);
      if (!next.delete(id)) {
        next.add(id);
      }
      return next;
    });
  }

  function toggleAll() {
    setPicked((current) => {
      const next = new Set(current);
      for (const tag of found) {
        if (allPicked) {
          next.delete(tag.id);
        } else {
          next.add(tag.id);
        }
      }
      return next;
    });
  }

  function toPrint(chosen: PriceTag[]) {
    addToForm(chosen);
    setNotice(
      `В форму печати ${plural(chosen.length, "добавлен", "добавлено", "добавлено")} ` +
        `${chosen.length} ${plural(chosen.length, "ценник", "ценника", "ценников")}`,
    );
  }

  async function remove(chosen: PriceTag[]) {
    const single = chosen.length === 1 ? chosen[0] : undefined;
    const confirmed = await ask({
      title: single
        ? "Удалить ценник из базы?"
        : `Удалить ${chosen.length} ${plural(chosen.length, "ценник", "ценника", "ценников")} из базы?`,
      text: single
        ? `«${single.name}» больше не будет в подсказках. Напечатанный снова, он вернётся в базу.`
        : "Они больше не будут в подсказках. Напечатанные снова, они вернутся в базу.",
      action: "Удалить",
      danger: true,
    });
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const removed = new Set<number>();
    try {
      for (const tag of chosen) {
        await deletePriceTag(tag.id);
        removed.add(tag.id);
      }
      setEditing(null);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setTags((current) => current?.filter((tag) => !removed.has(tag.id)) ?? null);
      setPicked((current) => new Set([...current].filter((id) => !removed.has(id))));
      if (removed.size > 0) {
        setNotice(
          `${plural(removed.size, "Удалён", "Удалено", "Удалено")} ${removed.size} ` +
            plural(removed.size, "ценник", "ценника", "ценников"),
        );
      }
      setBusy(false);
    }
  }

  function saved(tag: PriceTag) {
    setTags((current) => current?.map((item) => (item.id === tag.id ? tag : item)) ?? null);
    setEditing(null);
    setNotice(`Ценник «${tag.name}» сохранён`);
  }

  const total = tags?.length ?? 0;

  return (
    <main className="page">
      <PageHead
        title="Ценники"
        meta={
          tags &&
          `В базе ${total} ${plural(total, "ценник", "ценника", "ценников")}, они подсказываются при печати`
        }
      >
        <input
          className="input search"
          type="search"
          placeholder="Название, жирность, производитель"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </PageHead>

      <PriceTagTabs current="price-tag-base" go={go} />

      <div className="list-head">
        <div className="segments" role="tablist" aria-label="Размер">
          <SlidingThumb selector=".segment.active" className="segment-thumb" />
          <button
            type="button"
            role="tab"
            aria-selected={size === "all"}
            className={size === "all" ? "segment active" : "segment"}
            onClick={() => setSize("all")}
          >
            Все · {total}
          </button>
          {SIZES.map((option) => (
            <button
              key={option.key}
              type="button"
              role="tab"
              aria-selected={size === option.key}
              className={size === option.key ? "segment active" : "segment"}
              onClick={() => setSize(option.key)}
            >
              {option.label} · {counts.get(option.key) ?? 0}
            </button>
          ))}
        </div>
        {picked.size > 0 && (
          <div className="list-tools">
            <span className="price-tag-picked">Выбрано {picked.size}</span>
            <button type="button" className="button button-ghost" onClick={() => setPicked(new Set())}>
              Снять
            </button>
            <button
              type="button"
              className="button button-ghost price-tag-delete"
              disabled={busy}
              onClick={() => void remove(pickedTags)}
            >
              Удалить
            </button>
            <button
              type="button"
              className="button button-primary"
              onClick={() => {
                toPrint(pickedTags);
                setPicked(new Set());
              }}
            >
              В печать
            </button>
          </div>
        )}
      </div>

      {notice && (
        <p className="page-notice">
          {notice}
          {notice.startsWith("В форму печати") && (
            <>
              {" · "}
              <button
                type="button"
                className="price-tag-link"
                onClick={() => go({ page: "price-tags" })}
              >
                Перейти к печати
              </button>
            </>
          )}
        </p>
      )}
      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      {tags === null ? (
        !error && <span className="spinner page-spinner" />
      ) : (
        <section className="sheet">
          {found.length === 0 ? (
            <p className="list-empty">{total === 0 ? "Ценников пока нет" : "Ничего не найдено"}</p>
          ) : (
            <div className="table-wrap">
              <table className="list price-tag-base">
                <thead>
                  <tr>
                    <th className="pick-cell">
                      <input
                        type="checkbox"
                        className="pick-box"
                        aria-label="Отметить все найденные"
                        checked={allPicked}
                        onChange={toggleAll}
                      />
                    </th>
                    {COLUMNS.slice(0, 1).map((column) => (
                      <SortHead key={column.field} column={column} sort={sort} onSort={changeSort} />
                    ))}
                    <th>Размер</th>
                    <th>Ед.</th>
                    {COLUMNS.slice(1, 2).map((column) => (
                      <SortHead key={column.field} column={column} sort={sort} onSort={changeSort} />
                    ))}
                    <th>Производитель / страна</th>
                    {COLUMNS.slice(2).map((column) => (
                      <SortHead key={column.field} column={column} sort={sort} onSort={changeSort} />
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {found.map((tag) => (
                    <tr
                      key={tag.id}
                      className={`list-row clickable${picked.has(tag.id) ? " picked" : ""}`}
                      tabIndex={0}
                      title="Изменить ценник"
                      onClick={() => setEditing(tag)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          setEditing(tag);
                        }
                      }}
                    >
                      <td
                        className="pick-cell"
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          className="pick-box"
                          aria-label={`Отметить ${tag.name}`}
                          checked={picked.has(tag.id)}
                          onChange={() => toggle(tag.id)}
                        />
                      </td>
                      <td className="price-tag-base-name">
                        <span className="price-tag-base-title">{tag.name}</span>
                        {tag.subtitle && <span className="price-tag-subtitle">{tag.subtitle}</span>}
                      </td>
                      <td className="nowrap">{sizeLabel(tag.width_mm, tag.height_mm)}</td>
                      <td className="nowrap muted-cell">
                        {[UNIT_LABELS[tag.unit], tag.pack].filter(Boolean).join(" ")}
                      </td>
                      <td className="num strong nowrap">
                        {tag.price === null ? "—" : `${formatMoney(tag.price)} ₽`}
                      </td>
                      <td>
                        <span className="muted-cell">{ORIGIN_LABELS[tag.origin]}: </span>
                        {tag.origin_name}
                      </td>
                      <td className="nowrap muted-cell">{formatDateTime(tag.created_at)}</td>
                      <td className="row-actions">
                        <button
                          type="button"
                          className="row-action"
                          onClick={(event) => {
                            event.stopPropagation();
                            toPrint([tag]);
                          }}
                        >
                          В печать
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {editing && (
        <PriceTagDialog
          tag={editing}
          onClose={() => setEditing(null)}
          onSaved={saved}
          onDelete={(tag) => void remove([tag])}
        />
      )}
    </main>
  );
}

function SortHead({
  column,
  sort,
  onSort,
}: {
  column: (typeof COLUMNS)[number];
  sort: Sort;
  onSort: (field: SortField) => void;
}) {
  const active = sort.field === column.field;
  return (
    <th
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
}
