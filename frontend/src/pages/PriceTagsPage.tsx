import { useEffect, useState } from "react";

import { printPriceTags } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import Icon from "../components/icons";
import PageHead from "../components/PageHead";
import PriceTagSuggest, { MIN_QUERY, usePriceTagSearch } from "../components/PriceTagSuggest";
import PriceTagTabs from "../components/PriceTagTabs";
import ToggleField from "../components/ToggleField";
import { plural } from "../format";
import { message } from "../message";
import {
  ORIGIN_LABELS,
  SIZES,
  UNIT_LABELS,
  emptyRow,
  fillRow,
  isEmptyRow,
  loadRows,
  printRow,
  rowProblems,
  saveRows,
  type FormRow,
  type RowField,
  type SizeKey,
} from "../priceTags";
import type { Route } from "../router";
import type { PriceTag, PriceTagOrigin, PriceTagUnit } from "../types";

// a blob url lives as long as the page, the tab has read the file by then
const PDF_URL_LIFETIME_MS = 60_000;

interface Props {
  ask: Ask;
  go: (route: Route) => void;
}

export default function PriceTagsPage({ ask, go }: Props) {
  const [rows, setRows] = useState<FormRow[]>(loadRows);
  // the highlight of missing fields starts with the first try to print
  const [checked, setChecked] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // the name field being typed in, its row gets the suggestions
  const [focus, setFocus] = useState<{ key: number; anchor: HTMLElement } | null>(null);
  // escape or a pick hides the list until the name changes again
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(0);

  const focusedRow = focus ? rows.find((row) => row.key === focus.key) : undefined;
  const suggestions = usePriceTagSearch(focusedRow && !dismissed ? focusedRow.name : null);
  const listed = suggestions.found ?? [];
  const showList =
    focus !== null &&
    focusedRow !== undefined &&
    !dismissed &&
    focusedRow.name.trim().length >= MIN_QUERY &&
    (suggestions.found !== null || suggestions.error !== null);

  useEffect(() => saveRows(rows), [rows]);

  useEffect(() => setActive(0), [suggestions.found]);

  const filled = rows.filter((row) => !isEmptyRow(row));
  const problems = new Map(filled.map((row) => [row.key, rowProblems(row)]));
  const copies = filled.reduce((sum, row) => sum + (Number(row.quantity) || 0), 0);

  function update(key: number, change: Partial<FormRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...change } : row)));
    setNotice(null);
  }

  function pick(key: number, tag: PriceTag) {
    setRows((current) => current.map((row) => (row.key === key ? fillRow(row, tag) : row)));
    setDismissed(true);
    setNotice(null);
  }

  function addRow() {
    setRows((current) => [...current, emptyRow()]);
  }

  function removeRow(key: number) {
    setRows((current) => {
      const left = current.filter((row) => row.key !== key);
      return left.length > 0 ? left : [emptyRow()];
    });
  }

  async function clear() {
    if (filled.length > 0) {
      const confirmed = await ask({
        title: "Очистить форму?",
        text: "Все строки будут удалены. Сохранённые ценники останутся в подсказках.",
        action: "Очистить",
        danger: true,
      });
      if (!confirmed) {
        return;
      }
    }
    setRows([emptyRow()]);
    setChecked(false);
    setError(null);
    setNotice(null);
  }

  function invalid(key: number, field: RowField): boolean {
    return checked && (problems.get(key)?.has(field) ?? false);
  }

  function onNameKey(event: React.KeyboardEvent, key: number) {
    if (!showList) {
      return;
    }
    const count = listed.length;
    if (event.key === "Escape") {
      setDismissed(true);
    } else if (event.key === "ArrowDown" && count > 0) {
      event.preventDefault();
      setActive((index) => (index + 1) % count);
    } else if (event.key === "ArrowUp" && count > 0) {
      event.preventDefault();
      setActive((index) => (index - 1 + count) % count);
    } else if (event.key === "Enter" && listed[active]) {
      event.preventDefault();
      pick(key, listed[active]);
    }
  }

  async function createPdf() {
    setError(null);
    setNotice(null);
    if (filled.length === 0) {
      setError("Заполните хотя бы одну строку");
      return;
    }
    setChecked(true);
    if ([...problems.values()].some((fields) => fields.size > 0)) {
      setError("Заполните выделенные поля");
      return;
    }
    // the tab opens on the click itself, a tab opened after the answer is blocked as a popup
    const tab = window.open("", "_blank");
    setPrinting(true);
    try {
      const pdf = await printPriceTags(filled.map(printRow));
      const url = URL.createObjectURL(pdf);
      if (tab) {
        tab.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = "ценники.pdf";
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), PDF_URL_LIFETIME_MS);
      setNotice(
        `Готово: ${copies} ${plural(copies, "ценник", "ценника", "ценников")}, PDF открыт в новой вкладке`,
      );
    } catch (reason) {
      tab?.close();
      setError(message(reason));
    } finally {
      setPrinting(false);
    }
  }

  return (
    <main className="page">
      <PageHead
        title="Ценники"
        meta={
          copies > 0
            ? `${copies} ${plural(copies, "ценник", "ценника", "ценников")} к печати`
            : "Начните вводить название — подойдут ценники, которые уже печатали"
        }
      >
        <button type="button" className="button button-ghost" onClick={() => void clear()}>
          Очистить
        </button>
        <button
          type="button"
          className="button button-primary"
          disabled={printing}
          onClick={() => void createPdf()}
        >
          {printing ? "Создаём PDF…" : "Создать PDF"}
        </button>
      </PageHead>

      <PriceTagTabs current="price-tags" go={go} />
      {notice && <p className="page-notice">{notice}</p>}
      {error && <div className="alert price-tags-alert">{error}</div>}

      <section className="sheet">
        <div className="table-wrap">
          <table className="lines price-tags">
            <thead>
              <tr>
                <th className="num">№</th>
                <th>Размер, см</th>
                <th>Ед. изм.</th>
                <th>Граммовка</th>
                <th>Название</th>
                <th>Подназвание</th>
                <th className="num">Цена, руб.</th>
                <th className="num">коп.</th>
                <th>Производитель / страна</th>
                <th className="num">Кол-во</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.key} className="line">
                  <td className="num index">{index + 1}</td>
                  <td>
                    <select
                      className={`cell price-tag-size${invalid(row.key, "size") ? " cell-required" : ""}`}
                      aria-label="Размер"
                      value={row.size}
                      onChange={(event) =>
                        update(row.key, { size: event.target.value as SizeKey | "" })
                      }
                    >
                      <option value="">—</option>
                      {SIZES.map((size) => (
                        <option key={size.key} value={size.key}>
                          {size.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <ToggleField<PriceTagUnit>
                      label="Единица"
                      value={row.unit}
                      options={UNIT_LABELS}
                      onChange={(unit) => update(row.key, { unit })}
                    />
                  </td>
                  <td>
                    <input
                      className="cell price-tag-pack"
                      aria-label="Граммовка"
                      placeholder="напр. 500 г"
                      value={row.pack}
                      onChange={(event) => update(row.key, { pack: event.target.value })}
                    />
                  </td>
                  <td className="price-tag-name">
                    <textarea
                      className={`cell cell-name${invalid(row.key, "name") ? " cell-required" : ""}`}
                      aria-label="Название"
                      rows={1}
                      placeholder="Товар и марка"
                      value={row.name}
                      onFocus={(event) => {
                        setFocus({ key: row.key, anchor: event.currentTarget });
                        setDismissed(false);
                      }}
                      onBlur={() => setFocus(null)}
                      onKeyDown={(event) => onNameKey(event, row.key)}
                      onChange={(event) => {
                        update(row.key, { name: event.target.value });
                        setDismissed(false);
                      }}
                    />
                  </td>
                  <td className="price-tag-subtitle-cell">
                    <textarea
                      className="cell cell-name price-tag-sub"
                      aria-label="Подназвание"
                      rows={1}
                      placeholder="Жирность, вкус, сорт"
                      value={row.subtitle}
                      onChange={(event) => update(row.key, { subtitle: event.target.value })}
                    />
                  </td>
                  <td className="num">
                    <input
                      className={`cell cell-num price-tag-rub${invalid(row.key, "rub") ? " cell-required" : ""}`}
                      aria-label="Цена, рубли"
                      inputMode="numeric"
                      value={row.rub}
                      onChange={(event) => update(row.key, { rub: event.target.value })}
                    />
                  </td>
                  <td className="num">
                    <input
                      className={`cell cell-num cell-short${invalid(row.key, "kop") ? " cell-required" : ""}`}
                      aria-label="Цена, копейки"
                      inputMode="numeric"
                      placeholder="00"
                      maxLength={2}
                      value={row.kop}
                      onChange={(event) => update(row.key, { kop: event.target.value })}
                    />
                  </td>
                  <td className="price-tag-origin">
                    <ToggleField<PriceTagOrigin>
                      label="Подпись внизу"
                      value={row.origin}
                      options={ORIGIN_LABELS}
                      onChange={(origin) => update(row.key, { origin })}
                    />
                    <input
                      className={`cell${invalid(row.key, "originName") ? " cell-required" : ""}`}
                      aria-label={ORIGIN_LABELS[row.origin]}
                      placeholder={row.origin === "country" ? "напр. Россия" : "Название или город"}
                      value={row.originName}
                      onChange={(event) => update(row.key, { originName: event.target.value })}
                    />
                  </td>
                  <td className="num">
                    <input
                      className={`cell cell-num cell-short${invalid(row.key, "quantity") ? " cell-required" : ""}`}
                      aria-label="Количество"
                      inputMode="numeric"
                      value={row.quantity}
                      onChange={(event) => update(row.key, { quantity: event.target.value })}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="row-delete"
                      title="Удалить строку"
                      onClick={() => removeRow(row.key)}
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                        <path
                          d="M3.5 3.5l7 7M10.5 3.5l-7 7"
                          stroke="currentColor"
                          strokeWidth="1.4"
                        />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
              <tr className="row-add">
                <td />
                <td colSpan={10}>
                  <button type="button" className="add-line" onClick={addRow}>
                    <Icon name="plus" size={14} /> Добавить строку
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {showList && focus && focusedRow && (
        <PriceTagSuggest
          anchor={focus.anchor}
          suggestions={suggestions}
          active={active}
          onActive={setActive}
          onPick={(tag) => pick(focusedRow.key, tag)}
        />
      )}
    </main>
  );
}
