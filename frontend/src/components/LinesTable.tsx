import { Fragment, useCallback, useLayoutEffect, useRef, useState } from "react";

import { wordDiff } from "../diff";
import { formatMoney, formatNumber, formatSigned } from "../format";
import {
  emptyLine,
  toDecimal,
  toRubles,
  toText,
  trimDecimal,
  updateLine,
  type UpdateForm,
} from "../form";
import type {
  DraftForm,
  DraftLine,
  FormLine,
  InvoiceDraft,
  ProductSummary,
  SimilarProduct,
} from "../types";
import { IssueItem } from "./IssuesList";
import ProductPicker from "./ProductPicker";
import TotalsBlock from "./TotalsBlock";

interface Props {
  draft: InvoiceDraft;
  form: DraftForm;
  dirty: boolean;
  update: UpdateForm;
}

const COLUMNS = 13;
// the purchase columns hidden in the price view: price and sums without VAT, VAT, sum with VAT
const PURCHASE_DETAIL_COLUMNS = 4;
const VIEW_KEY = "lines-view";
// the issue code of a line with a close catalog product
const SIMILAR_PRODUCT = "similar_product";
// the issue code of a line that changes the shelf price of its product
const PRICE_CHANGED = "price_changed";

type View = "full" | "prices";

// the storage may be unavailable, the view then is not remembered
function savedView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "prices" ? "prices" : "full";
  } catch {
    return "full";
  }
}

function saveView(view: View) {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // nothing to do, the view is kept until the page is left
  }
}

interface NameProps {
  index: number;
  value: string | null;
  onChange: (value: string | null) => void;
}

function NameField({ index, value, onChange }: NameProps) {
  const field = useRef<HTMLTextAreaElement>(null);
  const resize = useCallback(() => {
    const element = field.current;
    if (!element) {
      return;
    }
    element.style.height = "auto";
    const border = element.offsetHeight - element.clientHeight;
    element.style.height = `${element.scrollHeight + border}px`;
  }, []);

  useLayoutEffect(resize, [resize, value]);

  useLayoutEffect(() => {
    const element = field.current;
    if (!element) {
      return;
    }
    let width = 0;
    let frame = 0;
    const observer = new ResizeObserver((entries) => {
      const nextWidth = entries[0]?.contentRect.width;
      // changing the height also notifies the observer, only a new width needs a resize
      if (nextWidth === undefined || nextWidth === width) {
        return;
      }
      width = nextWidth;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(resize);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [resize]);

  return (
    <textarea
      ref={field}
      className="cell cell-name"
      data-name-index={index}
      rows={1}
      value={value ?? ""}
      placeholder="Название"
      onChange={(event) => onChange(toText(event.target.value))}
    />
  );
}

interface CatalogProps {
  line: DraftLine | undefined;
  form: FormLine;
  // the name of a product picked since the last save, the draft does not know it yet
  pickedName: string | undefined;
  canPick: boolean;
  onOpen: (anchor: HTMLElement) => void;
  onUnlink: () => void;
}

// what the catalog knows about the line, shown under its name
function LineCatalog({ line, form, pickedName, canPick, onOpen, onUnlink }: CatalogProps) {
  let tag = null;
  if (form.product_id !== null) {
    // linked by hand, the name may differ and becomes another spelling when posted
    const name = line?.product_id === form.product_id ? line.product_name : pickedName;
    tag = (
      <span className="tag tag-linked" title={name ?? undefined}>
        <span className="tag-text">
          {name && name !== form.name ? `из каталога: ${name}` : "из каталога"}
        </span>
        <button type="button" className="tag-remove" title="Отвязать" onClick={onUnlink}>
          ×
        </button>
      </span>
    );
  } else if (line?.new_product && form.retail_price !== null) {
    // without a price the issue under the line already says it is new
    tag = <span className="tag tag-new">новый товар</span>;
  } else if (line?.product_id != null && line.product_name !== form.name) {
    // a known product under another spelling shows its catalog name
    tag = <span className="tag">в каталоге: {line.product_name}</span>;
  }
  if (!tag && !canPick) {
    return null;
  }
  return (
    <span className="line-catalog">
      {tag}
      {canPick && (
        <button
          type="button"
          className={form.name === null ? "line-pick always" : "line-pick"}
          onClick={(event) => onOpen(event.currentTarget.closest("td") ?? event.currentTarget)}
        >
          {form.product_id !== null ? "другой товар" : "выбрать из каталога"}
        </button>
      )}
    </span>
  );
}

interface SimilarProps {
  similar: SimilarProduct[];
  name: string;
  onLink: (product: SimilarProduct) => void;
}

// close catalog names for a line that found no product, the differing words marked
function SimilarHints({ similar, name, onLink }: SimilarProps) {
  return (
    <div className="similar">
      <div className="similar-head">
        <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        {similar.length > 1 ? "Похожие товары в каталоге" : "Похожий товар в каталоге"}
      </div>
      <ul className="similar-list">
        {similar.map((product) => (
          <li key={product.id} className="similar-item">
            <span className="similar-name" title={product.name}>
              {wordDiff(name, product.name).map((word, index) => (
                <Fragment key={index}>
                  {index > 0 && " "}
                  {word.changed ? <mark>{word.text}</mark> : word.text}
                </Fragment>
              ))}
            </span>
            <span
              className="similar-ratio"
              title="Совпадение названий"
              style={{ "--ratio": `${product.similarity}%` } as React.CSSProperties}
            >
              <span className="similar-meter" aria-hidden="true" />
              {product.similarity}%
            </span>
            <button type="button" className="similar-link" onClick={() => onLink(product)}>
              <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M3 8.5l3.2 3L13 4.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Это он
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// the cost with VAT against the last delivery of the product, shown only when it changed
function CostChange({ line }: { line: DraftLine | undefined }) {
  const previous = line?.previous_cost_price ?? null;
  const cost = line?.cost_price ?? null;
  if (previous === null || cost === null) {
    return null;
  }
  const diff = Number(cost) - Number(previous);
  // to a tenth of a percent, a free previous delivery has no percent
  const share = Number(previous) > 0 ? Math.round((Math.abs(diff) / Number(previous)) * 1000) / 10 : null;
  const percent = share === null ? "" : ` (${diff > 0 ? "+" : "−"}${formatNumber(share)}%)`;
  return (
    <span
      className={diff > 0 ? "cost-change cost-up" : "cost-change cost-down"}
      title="Цена с НДС в прошлой поставке"
    >
      <span>было {formatMoney(previous)}</span>
      <span>
        {formatSigned(diff)}
        {percent}
      </span>
    </span>
  );
}

interface RevalueProps {
  line: DraftLine | undefined;
  form: FormLine;
  onChange: (quantity: string | null) => void;
}

// the old stock on the shelf, it takes the new price when the invoice is posted
function RevalueField({ line, form, onChange }: RevalueProps) {
  const previous = line?.previous_retail_price ?? null;
  const price = line?.retail_price ?? null;
  const quantity = form.revalue_quantity;
  const amount =
    previous !== null && price !== null && quantity !== null && !Number.isNaN(Number(quantity))
      ? Number(quantity) * (Number(price) - Number(previous))
      : null;
  return (
    <div className="revalue">
      <span className="revalue-text">
        {previous !== null && price !== null ? (
          <>
            Цена на полке: {formatNumber(previous)} → <strong>{formatNumber(price)} ₽</strong>
          </>
        ) : (
          "Цена на полке не меняется"
        )}
      </span>
      <label className="revalue-field">
        Осталось старого товара
        <input
          className="cell cell-num cell-short"
          inputMode="decimal"
          placeholder="0"
          value={quantity ?? ""}
          onChange={(event) => onChange(toDecimal(event.target.value))}
        />
        {form.unit && <span className="revalue-unit">{form.unit}</span>}
      </label>
      {amount !== null ? (
        <span className="revalue-amount">переоценка {formatSigned(amount)} ₽</span>
      ) : (
        <span className="revalue-hint">пусто, если старого товара нет</span>
      )}
    </div>
  );
}

export default function LinesTable({ draft, form, dirty, update }: Props) {
  const supplierId = form.supplier !== null && "id" in form.supplier ? form.supplier.id : null;
  const [picker, setPicker] = useState<{ lineNo: number; anchor: HTMLElement } | null>(null);
  const [pickedNames, setPickedNames] = useState<Record<number, string>>({});
  const [view, setView] = useState<View>(savedView);
  // the pinned name column gets its edge only once the table is scrolled sideways
  const [scrolled, setScrolled] = useState(false);
  const closePicker = useCallback(() => setPicker(null), []);
  const linesByNumber = new Map(draft.lines.map((line) => [line.line, line]));
  const full = view === "full";
  const columns = full ? COLUMNS : COLUMNS - PURCHASE_DETAIL_COLUMNS;

  function changeView(next: View) {
    setView(next);
    saveView(next);
  }

  function pick(lineNo: number, product: ProductSummary) {
    setPickedNames((names) => ({ ...names, [product.id]: product.name }));
    // a line typed by hand takes the catalog values, a printed one keeps what was printed
    update((current) => ({
      ...current,
      lines: current.lines.map((line) =>
        line.line_no === lineNo
          ? {
              ...line,
              product_id: product.id,
              name: line.name ?? product.name,
              unit: line.unit ?? product.unit,
              vat_percent: line.vat_percent ?? trimDecimal(product.vat_percent),
            }
          : line,
      ),
    }));
    setPicker(null);
  }

  // the index of the next line with a new product in the given direction, -1 when there is none
  function newProductIndex(index: number, step: number): number {
    let target = index + step;
    while (
      target >= 0 &&
      target < form.lines.length &&
      !linesByNumber.get(form.lines[target]!.line_no)?.new_product
    ) {
      target += step;
    }
    return target < form.lines.length ? target : -1;
  }

  // tab or enter from a retail price goes to the price of the next new product, with shift to the previous one
  // the iPad on-screen keyboard has no tab, its next key sends enter
  function jumpToNewProduct(event: React.KeyboardEvent<HTMLInputElement>, index: number) {
    const enter = event.key === "Enter";
    if ((event.key !== "Tab" && !enter) || event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }
    const target = newProductIndex(index, event.shiftKey ? -1 : 1);
    const input = event.currentTarget
      .closest("table")
      ?.querySelector<HTMLInputElement>(`[data-retail-index="${target}"]`);
    // past the last new product the tab moves on as usual, the enter hides the keyboard
    if (input) {
      event.preventDefault();
      input.focus();
      input.select();
    } else if (enter) {
      event.preventDefault();
      event.currentTarget.blur();
    }
  }

  function addLine(button: HTMLElement) {
    const index = form.lines.length;
    // reserve the source numbers even when their rows have been removed
    const sourceMax =
      Math.max(0, ...draft.extraction.items.map((item) => Number(item.line_no ?? 0))) +
      draft.extraction.items.filter((item) => item.line_no === null).length;
    const lineNo = Math.max(sourceMax, ...form.lines.map((line) => line.line_no)) + 1;
    update((current) => ({ ...current, lines: [...current.lines, emptyLine(lineNo)] }));
    if (supplierId === null) {
      return;
    }
    // a line added by hand starts from the catalog, opened under the new row once it is rendered
    const table = button.closest("table");
    requestAnimationFrame(() => {
      const cell = table?.querySelector(`[data-name-index="${index}"]`)?.closest("td");
      if (cell) {
        setPicker({ lineNo, anchor: cell });
      }
    });
  }

  return (
    <section className="sheet">
      <div className="sheet-tools">
        <div className="segments" role="tablist" aria-label="Колонки таблицы">
          <button
            type="button"
            role="tab"
            aria-selected={full}
            className={full ? "segment active" : "segment"}
            onClick={() => changeView("full")}
          >
            Все колонки
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={!full}
            className={full ? "segment" : "segment active"}
            onClick={() => changeView("prices")}
          >
            Только цены
          </button>
        </div>
      </div>
      <div
        className={scrolled ? "table-wrap scrolled" : "table-wrap"}
        onScroll={(event) => setScrolled(event.currentTarget.scrollLeft > 0)}
      >
        <table className={`lines${full ? "" : " lines-prices"}${dirty ? " stale" : ""}`}>
          <colgroup>
            <col className="col-no" />
            <col className="col-name" />
          </colgroup>
          <thead>
            <tr className="groups">
              <th colSpan={4} />
              {/* the shelf price is typed by hand, so it sits next to the quantity, not at the far right */}
              <th className="group group-start retail">Розница</th>
              <th colSpan={full ? 5 : 1} className="group group-start">
                Закупка
              </th>
              <th colSpan={2} className="group group-start retail">
                Розница
              </th>
              <th />
            </tr>
            <tr>
              <th className="num sticky-no">№</th>
              <th className="sticky-name">Название</th>
              <th className="num">Кол-во</th>
              <th>Ед.</th>
              <th className="num group-start retail">Цена</th>
              {full && (
                <>
                  <th className="num group-start">Цена без НДС</th>
                  <th className="num">НДС, %</th>
                </>
              )}
              <th className={full ? "num" : "num group-start"}>Цена с НДС</th>
              {full && (
                <>
                  <th className="num">Сумма без НДС</th>
                  <th className="num">Сумма с НДС</th>
                </>
              )}
              <th className="num group-start retail">Наценка, %</th>
              <th className="num retail">Сумма</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {form.lines.map((formLine, index) => {
              const position = formLine.line_no;
              const line = linesByNumber.get(position);
              const issues = draft.issues.filter((issue) => issue.line === position);
              const blocked = issues.some((issue) => issue.blocking);
              const rowClass = blocked ? "row-blocking" : issues.length > 0 ? "row-warning" : "";
              // a similar product and a price change are shown with their own controls, not as text
              const listed = issues.filter(
                (issue) => issue.code !== SIMILAR_PRODUCT && issue.code !== PRICE_CHANGED,
              );
              // the field stays once filled, the warning goes away with it
              const revalue =
                issues.some((issue) => issue.code === PRICE_CHANGED) ||
                formLine.revalue_quantity !== null;
              return (
                <Fragment key={position}>
                  <tr className={`line ${rowClass}`}>
                    <td className="num index sticky-no">{position}</td>
                    <td className="line-name sticky-name">
                      <NameField
                        index={index}
                        value={formLine.name}
                        onChange={(name) => updateLine(update, index, { name })}
                      />
                      <LineCatalog
                        line={line}
                        form={formLine}
                        pickedName={
                          formLine.product_id !== null ? pickedNames[formLine.product_id] : undefined
                        }
                        canPick={supplierId !== null}
                        onOpen={(anchor) => setPicker({ lineNo: position, anchor })}
                        onUnlink={() => updateLine(update, index, { product_id: null })}
                      />
                      {formLine.product_id === null && formLine.name && line?.similar.length ? (
                        <SimilarHints
                          similar={line.similar}
                          name={formLine.name}
                          onLink={(product) => {
                            setPickedNames((names) => ({ ...names, [product.id]: product.name }));
                            // the printed name stays and becomes another spelling when posted
                            updateLine(update, index, { product_id: product.id });
                          }}
                        />
                      ) : null}
                    </td>
                    <td className="num">
                      <input
                        className="cell cell-num"
                        inputMode="decimal"
                        value={formLine.quantity ?? ""}
                        onChange={(event) =>
                          updateLine(update, index, { quantity: toDecimal(event.target.value) })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="cell cell-unit"
                        value={formLine.unit ?? ""}
                        onChange={(event) =>
                          updateLine(update, index, { unit: toText(event.target.value) })
                        }
                      />
                    </td>
                    <td className="num group-start retail">
                      <input
                        className={
                          line?.new_product && formLine.retail_price === null
                            ? "cell cell-num cell-required"
                            : "cell cell-num"
                        }
                        inputMode="numeric"
                        enterKeyHint={newProductIndex(index, 1) === -1 ? "done" : "next"}
                        data-retail-index={index}
                        // empty means the price by the current markup
                        placeholder={line?.retail_price ? formatNumber(line.retail_price) : "₽"}
                        value={formLine.retail_price ?? ""}
                        onChange={(event) =>
                          updateLine(update, index, { retail_price: toRubles(event.target.value) })
                        }
                        onKeyDown={(event) => jumpToNewProduct(event, index)}
                      />
                    </td>
                    {full && (
                      <>
                        <td className="num computed group-start">
                          {formatMoney(line?.base_price ?? null)}
                        </td>
                        <td className="num">
                          <input
                            className="cell cell-num cell-short"
                            inputMode="decimal"
                            placeholder="—"
                            value={formLine.vat_percent ?? ""}
                            onChange={(event) =>
                              updateLine(update, index, {
                                vat_percent: toDecimal(event.target.value),
                              })
                            }
                          />
                        </td>
                      </>
                    )}
                    <td className={full ? "num computed" : "num computed group-start"}>
                      {formatMoney(line?.cost_price ?? null)}
                      <CostChange line={line} />
                    </td>
                    {full && (
                      <>
                        <td className="num computed">
                          {formatMoney(line?.base_price_total ?? null)}
                        </td>
                        <td className="num">
                          <input
                            className="cell cell-num cell-money"
                            inputMode="decimal"
                            value={formLine.cost_price_total ?? ""}
                            onChange={(event) =>
                              updateLine(update, index, {
                                cost_price_total: toDecimal(event.target.value),
                              })
                            }
                          />
                        </td>
                      </>
                    )}
                    <td className="num computed group-start retail">
                      {formatNumber(line?.markup_pct ?? null)}
                    </td>
                    <td className="num computed strong retail">
                      {formatMoney(line?.retail_price_total ?? null)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="row-delete"
                        title="Удалить строку"
                        onClick={() =>
                          update((current) => ({
                            ...current,
                            lines: current.lines.filter((_, position) => position !== index),
                          }))
                        }
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                          <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeWidth="1.4" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                  {revalue && (
                    <tr className={`row-issues ${rowClass}`}>
                      <td />
                      <td colSpan={columns - 1}>
                        <RevalueField
                          line={line}
                          form={formLine}
                          onChange={(quantity) =>
                            updateLine(update, index, { revalue_quantity: quantity })
                          }
                        />
                      </td>
                    </tr>
                  )}
                  {listed.length > 0 && (
                    <tr className={`row-issues ${rowClass}`}>
                      <td />
                      <td colSpan={columns - 1}>
                        {listed.map((issue, issueIndex) => (
                          <IssueItem key={issueIndex} issue={issue} />
                        ))}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            <tr className="row-add">
              <td />
              <td colSpan={columns - 1}>
                <button
                  type="button"
                  className="add-line"
                  onClick={(event) => addLine(event.currentTarget)}
                >
                  + Строка
                </button>
              </td>
            </tr>
          </tbody>
          <TotalsBlock draft={draft} full={full} />
        </table>
      </div>
      {picker &&
        supplierId !== null &&
        form.lines.some((line) => line.line_no === picker.lineNo) && (
          <ProductPicker
            supplierId={supplierId}
            anchor={picker.anchor}
            onPick={(product) => pick(picker.lineNo, product)}
            onClose={closePicker}
          />
        )}
    </section>
  );
}
