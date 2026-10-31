import { Fragment, useEffect, useState } from "react";

import { clearDraftOrder, confirmOrder, getOrder, listOrders, removeOrderItem } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import OrderItemDialog, { type OrderTarget } from "../components/OrderItemDialog";
import PageHead from "../components/PageHead";
import { formatDateTime, formatMoney, formatNumber, formatText, plural } from "../format";
import { message } from "../message";
import type { Route } from "../router";
import type { Order, OrderLine, OrderListItem } from "../types";

interface Props {
  ask: Ask;
  go: (route: Route) => void;
  // the order being filled, null when it is empty, undefined until it is loaded
  cart: Order | null | undefined;
  onCart: (cart: Order | null) => void;
}

const PAGE = 50;

interface SupplierGroup {
  id: number;
  name: string;
  lines: OrderLine[];
  total: number;
}

// the api sorts the lines by supplier, a group starts where the supplier changes
function groups(lines: OrderLine[]): SupplierGroup[] {
  const result: SupplierGroup[] = [];
  for (const line of lines) {
    const last = result.at(-1);
    const group =
      last && last.id === line.supplier_id
        ? last
        : { id: line.supplier_id, name: line.supplier_name, lines: [], total: 0 };
    if (group !== last) {
      result.push(group);
    }
    group.lines.push(line);
    group.total += line.cost_total === null ? 0 : Number(line.cost_total);
  }
  return result;
}

function positions(count: number): string {
  return `${count} ${plural(count, "позиция", "позиции", "позиций")}`;
}

function approx(value: string | number): string {
  return Number(value) > 0 ? `≈ ${formatMoney(value)} ₽` : formatText(null);
}

function quantity(line: OrderLine): string {
  return `${formatNumber(line.quantity)}${line.unit ? ` ${line.unit}` : ""}`;
}

// the lines by supplier, the cart ones open the quantity dialog and can be removed
function OrderLines({
  order,
  busy,
  onEdit,
  onRemove,
}: {
  order: Order;
  busy?: boolean;
  onEdit?: (line: OrderLine) => void;
  onRemove?: (line: OrderLine) => void;
}) {
  return (
    <div className="order-groups">
      {groups(order.lines).map((group) => (
        <div key={group.id} className="order-group">
          <div className="order-group-head">
            <span className="order-group-name">{group.name}</span>
            <span className="order-group-meta">
              {positions(group.lines.length)}
              {group.total > 0 && ` · ${approx(group.total)}`}
            </span>
          </div>
          <div className="table-wrap">
            <table className="list order-table">
              <thead>
                <tr>
                  <th>Товар</th>
                  <th className="num">Кол-во</th>
                  <th className="num order-col-price">Закупка</th>
                  <th className="num">Сумма</th>
                  {onRemove && (
                    <th>
                      <span className="visually-hidden">Убрать</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {group.lines.map((line) => (
                  <tr
                    key={line.product_id}
                    className={onEdit ? "list-row clickable" : "list-row"}
                    tabIndex={onEdit ? 0 : undefined}
                    title={onEdit ? "Изменить количество" : undefined}
                    onClick={() => onEdit?.(line)}
                    onKeyDown={(event) => {
                      if (onEdit && event.key === "Enter") {
                        onEdit(line);
                      }
                    }}
                  >
                    <td className="order-line-name">{line.name}</td>
                    <td className="num nowrap strong">{quantity(line)}</td>
                    <td className="num nowrap muted-cell order-col-price">
                      {line.cost_price === null
                        ? formatText(null)
                        : `${formatMoney(line.cost_price)} ₽`}
                    </td>
                    <td className="num nowrap">
                      {line.cost_total === null ? (
                        <span className="muted-cell">нет цены</span>
                      ) : (
                        `${formatMoney(line.cost_total)} ₽`
                      )}
                    </td>
                    {onRemove && (
                      // the row opens the quantity dialog, the button only removes
                      <td
                        className="order-line-remove"
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="row-delete"
                          aria-label={`Убрать из заказа: ${line.name}`}
                          title="Убрать из заказа"
                          disabled={busy}
                          onClick={() => onRemove(line)}
                        >
                          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                            <path
                              d="M4 4l8 8M12 4l-8 8"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.6"
                              strokeLinecap="round"
                            />
                          </svg>
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function OrderTotal({ order }: { order: Order }) {
  const unpriced = order.lines.filter((line) => line.cost_total === null).length;
  return (
    <div className="order-total">
      <span className="order-total-label">Итого по закупочным ценам</span>
      <strong className="order-total-value">{approx(order.total)}</strong>
      {unpriced > 0 && (
        <span className="order-total-note">
          без {unpriced} {plural(unpriced, "товара", "товаров", "товаров")} — их ещё не закупали
        </span>
      )}
    </div>
  );
}

export default function OrdersPage({ ask, go, cart, onCart }: Props) {
  const [history, setHistory] = useState<OrderListItem[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  // the confirmed orders unfolded in the list, with their lines once loaded
  const [opened, setOpened] = useState<Set<number>>(() => new Set());
  const [details, setDetails] = useState<Map<number, Order>>(() => new Map());
  const [editing, setEditing] = useState<OrderTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // bumped after a confirmation to load the history again
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    listOrders(PAGE, 0)
      .then((page) => {
        if (current) {
          setHistory(page.items);
          setHasMore(page.has_more);
        }
      })
      .catch((reason) => current && setError(message(reason)));
    return () => {
      current = false;
    };
  }, [version]);

  async function more() {
    if (!history) {
      return;
    }
    setLoadingMore(true);
    try {
      const page = await listOrders(PAGE, history.length);
      setHistory([...history, ...page.items]);
      setHasMore(page.has_more);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  async function toggle(id: number) {
    const next = new Set(opened);
    if (!next.delete(id)) {
      next.add(id);
    }
    setOpened(next);
    if (!next.has(id) || details.has(id)) {
      return;
    }
    try {
      const order = await getOrder(id);
      setDetails((previous) => new Map(previous).set(id, order));
    } catch (reason) {
      setError(message(reason));
    }
  }

  // the cart changes one request at a time, a second click waits for the first
  async function change(send: () => Promise<Order | null>, text: string) {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onCart(await send());
      setNotice(text);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  function remove(line: OrderLine) {
    void change(() => removeOrderItem(line.product_id), `«${line.name}» убран из заказа`);
  }

  async function clear() {
    const ok = await ask({
      title: "Очистить заказ?",
      text: "Все товары уберутся из текущего заказа.",
      action: "Очистить",
      danger: true,
    });
    if (ok) {
      await change(async () => {
        await clearDraftOrder();
        return null;
      }, "Заказ очищен");
    }
  }

  async function confirm(order: Order) {
    const ok = await ask({
      title: "Подтвердить заказ?",
      text: `${positions(order.lines.length)}. После подтверждения заказ уйдёт в историю и изменить его будет нельзя.`,
      action: "Подтвердить",
    });
    if (!ok) {
      return;
    }
    await change(async () => {
      const confirmed = await confirmOrder();
      // the new order opens at the top of the history
      setDetails((previous) => new Map(previous).set(confirmed.id, confirmed));
      setOpened((previous) => new Set(previous).add(confirmed.id));
      setVersion((previous) => previous + 1);
      return null;
    }, `Заказ №${order.id} подтверждён`);
  }

  function edit(line: OrderLine) {
    setEditing({
      productId: line.product_id,
      name: line.name,
      supplierName: line.supplier_name,
      unit: line.unit,
      costPrice: line.cost_price,
      quantity: line.quantity,
    });
  }

  const supplierCount = cart ? groups(cart.lines).length : 0;

  return (
    <main className="page orders-page">
      <PageHead title="Заказы" />
      {notice && <p className="page-notice">{notice}</p>}
      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      <div className="section-head">
        <h2 className="section-title">Текущий заказ</h2>
        {cart && (
          <span className="section-meta">
            {positions(cart.lines.length)} · {supplierCount}{" "}
            {plural(supplierCount, "поставщик", "поставщика", "поставщиков")}
            {" · "}
            <span className="status-dot status-draft">не подтверждён</span>
          </span>
        )}
      </div>

      {cart === null && (
        <section className="sheet order-empty">
          <p className="order-empty-title">Заказ пуст</p>
          <p className="order-empty-text">
            Нажмите «В заказ» у нужных товаров — они соберутся здесь.
          </p>
          <button
            type="button"
            className="button button-soft"
            onClick={() => go({ page: "catalog" })}
          >
            Перейти к товарам
          </button>
        </section>
      )}

      {cart && (
        <section className="sheet">
          <OrderLines order={cart} busy={busy} onEdit={edit} onRemove={remove} />
          <footer className="order-foot">
            <OrderTotal order={cart} />
            <div className="order-actions">
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() => void clear()}
              >
                Очистить
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => go({ page: "catalog" })}
              >
                Добавить товары
              </button>
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={() => void confirm(cart)}
              >
                Подтвердить заказ
              </button>
            </div>
          </footer>
        </section>
      )}

      <div className="section-head">
        <h2 className="section-title">Подтверждённые</h2>
      </div>

      {history && (
        <section className="sheet">
          {history.length === 0 ? (
            <p className="list-empty">Подтверждённых заказов пока нет</p>
          ) : (
            <div className="table-wrap">
              <table className="list">
                <thead>
                  <tr>
                    <th>Заказ</th>
                    <th>Подтверждён</th>
                    <th>Поставщики</th>
                    <th className="num">Позиций</th>
                    <th className="num">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => {
                    const open = opened.has(item.id);
                    const detail = details.get(item.id);
                    return (
                      <Fragment key={item.id}>
                        <tr
                          className="list-row clickable"
                          tabIndex={0}
                          aria-expanded={open}
                          onClick={() => void toggle(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              void toggle(item.id);
                            }
                          }}
                        >
                          <td className="nowrap">
                            <span className="order-number">
                              <svg
                                className={
                                  open ? "chevron catalog-chevron open" : "chevron catalog-chevron"
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
                              №{item.id}
                            </span>
                          </td>
                          <td className="nowrap muted-cell">{formatDateTime(item.confirmed_at)}</td>
                          <td className="list-supplier">{item.supplier_names.join(", ")}</td>
                          <td className="num muted-cell">{item.lines}</td>
                          <td className="num nowrap strong">{approx(item.total)}</td>
                        </tr>
                        {open && (
                          <tr className="order-detail">
                            <td colSpan={5}>
                              {detail ? (
                                <>
                                  <OrderLines order={detail} />
                                  <footer className="order-foot">
                                    <OrderTotal order={detail} />
                                  </footer>
                                </>
                              ) : (
                                <p className="list-empty">Загрузка…</p>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {hasMore && (
        <div className="more">
          <button
            type="button"
            className="button button-ghost"
            disabled={loadingMore}
            onClick={more}
          >
            Показать ещё
          </button>
        </div>
      )}

      {editing && (
        <OrderItemDialog
          key={editing.productId}
          target={editing}
          onClose={() => setEditing(null)}
          onSaved={(next, text) => {
            setEditing(null);
            setNotice(text);
            onCart(next);
          }}
        />
      )}
    </main>
  );
}
