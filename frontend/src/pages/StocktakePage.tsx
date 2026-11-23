import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, ensureSession, request } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import PageHead from "../components/PageHead";
import StocktakeLines from "../components/StocktakeLines";
import StocktakeName from "../components/StocktakeName";
import { formatDateTime, formatMoney, formatQuantityFromAmount } from "../format";
import { message } from "../message";
import type { Route } from "../router";
import { watchStocktake } from "../stocktakeEvents";
import { apiPath } from "../stores";
import {
  blankDraft,
  changeLine,
  hasInput,
  lineCount,
  nameKey,
  persistDraft,
  requestId,
  restoreDraft,
  stocktakeBalance,
  stocktakeHint,
  type CountDocument,
  type CountDraft,
  type CountLine,
  type LineFields,
  type Unit,
} from "../stocktakes";

interface Props {
  id: number;
  userId: number;
  go: (route: Route) => void;
  ask: Ask;
}

const moneyPattern = "[0-9]{1,12}([.,][0-9]{1,2})?";

function useDocument(id: number) {
  const latest = useRef<CountDocument | null>(null);
  const [doc, setDoc] = useState<CountDocument | null>(null);
  const [syncError, setSyncError] = useState("");
  const [disconnected, setDisconnected] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const version = latest.current?.version;
      const result = await request<CountDocument | null>(
        "GET",
        `/stocktakes/${id}${version ? `?since=${version}` : ""}`,
      );
      if (result && result.version > (latest.current?.version ?? 0)) {
        latest.current = result;
        setDoc(result);
      }
      setSyncError("");
      return latest.current;
    } catch (reason) {
      setSyncError(message(reason));
      return null;
    }
  }, [id]);

  useEffect(() => {
    const url = new URL(apiPath("gastronom", `/stocktakes/${id}/events`), window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return watchStocktake({
      url,
      currentVersion: () => latest.current?.version ?? 0,
      refresh,
      ensureSession,
      setDisconnected,
    });
  }, [id, refresh]);
  return {
    doc,
    syncError: syncError || (disconnected ? "Восстанавливаем связь для обновлений переучёта…" : ""),
    refresh,
  };
}

function totals(doc: CountDocument) {
  return `${lineCount(doc.line_count)} · ${formatMoney(doc.total)} ₽`;
}

export default function StocktakePage({ id, userId, go, ask }: Props) {
  const { doc, syncError, refresh } = useDocument(id);
  const storageKey = `gastronom:stocktake:${userId}:${id}`;
  const [form, setForm] = useState(() => restoreDraft(storageKey));
  const draft = useRef(form);
  const [correcting, setCorrecting] = useState(form.correction && hasInput(form));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [storageError, setStorageError] = useState(false);
  const [duplicateId, setDuplicateId] = useState<number | null>(null);
  const [lineQuery, setLineQuery] = useState("");
  const [highlight, setHighlight] = useState<number | null>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const balanceInput = useRef<HTMLInputElement>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const editable = Boolean(doc && (!doc.completed_at || correcting));
  const dirty = hasInput(form);
  const pendingRemoval = form.pending === "save" ? null : form.pending;
  const removalName = pendingRemoval && (
    pendingRemoval.name || doc?.lines.find((line) => line.id === pendingRemoval.id)?.name
  );
  const calculatedQuantity = form.byAmount ? formatQuantityFromAmount(form.enteredAmount, form.price) : null;
  const currentLine = doc?.lines.find((line) => line.id === form.lineId);
  const changed = Boolean(form.lineId && doc && currentLine?.version !== form.version);
  const key = nameKey(form.name);
  const duplicate = doc?.lines.find(
    (line) => line.id !== form.lineId && (nameKey(line.name) === key || line.id === duplicateId),
  );

  const remember = useCallback(
    (next: CountDraft) => {
      setStorageError(!persistDraft(storageKey, next, draft.current.requestId));
      draft.current = next;
      setForm(next);
    },
    [storageKey],
  );
  function fields(values: Partial<LineFields>) {
    remember({ ...form, ...values, requestId: requestId(), correction: correcting });
    setError("");
    setDuplicateId(null);
  }
  const mark = useCallback((lineId: number) => {
    window.clearTimeout(timer.current);
    setHighlight(lineId);
    timer.current = window.setTimeout(() => setHighlight(null), 2200);
  }, []);
  const previousTop = useRef<number | null>(null);
  const newest = doc ? (doc.lines[0]?.id ?? 0) : null;
  useEffect(() => {
    if (newest !== null && previousTop.current !== null && newest > previousTop.current)
      mark(newest);
    previousTop.current = newest;
  }, [newest, mark]);
  function reset() {
    remember(blankDraft());
    setError("");
    setDuplicateId(null);
  }
  const loadLine = useCallback(
    (line: CountLine) => {
      remember({
        ...blankDraft(),
        name: line.name,
        unit: line.unit,
        price: line.price?.replace(".", ",") ?? "",
        quantity: line.quantity === null ? "" : String(Number(line.quantity)).replace(".", ","),
        byAmount: line.quantity === null,
        enteredAmount: line.quantity === null ? line.amount.replace(".", ",") : "",
        version: line.version,
        lineId: line.id,
        correction: correcting,
      });
      setError("");
      setDuplicateId(null);
      requestAnimationFrame(() => {
        balanceInput.current?.focus();
        balanceInput.current?.select();
      });
    },
    [correcting, remember],
  );
  const edit = useCallback(
    async (line: CountLine, source: "list" | "suggestion" = "list") => {
      const current = draft.current;
      // the typed name is the search query when picking a suggestion
      const replacingInput = hasInput(source === "suggestion" ? { ...current, name: "" } : current);
      if (
        replacingInput &&
        !(await ask({
          title: "Перейти к другой строке?",
          text: "Текущий ввод будет заменён.",
          action: "Перейти",
        }))
      )
        return;
      loadLine(line);
    },
    [ask, loadLine],
  );

  const submit = useCallback(async (sent: CountDraft) => {
    if (busy || !sent.pending) return;
    const removal = sent.pending === "save" ? null : sent.pending;
    setBusy(true);
    setDeleteError("");
    if (!removal || removal.id === sent.lineId) {
      setError("");
      setDuplicateId(null);
    }
    remember(sent);
    try {
      const result = await changeLine(id, sent);
      if (removal && removal.id !== sent.lineId) {
        remember({ ...sent, pending: null, requestId: requestId() });
      } else {
        remember(blankDraft());
      }
      if (!removal) mark(result.line_id);
      await refresh();
      requestAnimationFrame(() => {
        if (removal) document.getElementById("stocktake-positions")?.focus({ preventScroll: true });
        else nameInput.current?.focus();
      });
    } catch (reason) {
      if (removal) setDeleteError(message(reason));
      else setError(message(reason));
      if (
        reason instanceof ApiError &&
        reason.status >= 400 &&
        reason.status < 500 &&
        reason.status !== 401
      ) {
        remember({ ...sent, pending: null, requestId: requestId() });
        const detail = reason.detail as { code?: string; line_id?: number } | null;
        if (detail?.code === "duplicate") setDuplicateId(detail.line_id ?? null);
        await refresh();
      }
    } finally {
      setBusy(false);
    }
  }, [busy, id, mark, refresh, remember]);

  const remove = useCallback(async (line: CountLine) => {
    const confirmed = await ask({
      title: "Удалить позицию?",
      text: draft.current.lineId === line.id
        ? `«${line.name}». Ввод для этой позиции тоже будет очищен.`
        : line.name,
      action: "Удалить",
      danger: true,
    });
    if (confirmed) {
      await submit({
        ...draft.current,
        pending: { id: line.id, version: line.version, name: line.name },
        requestId: requestId(),
        correction: correcting,
      });
    }
  }, [ask, correcting, submit]);

  async function complete(initial: CountDocument) {
    setBusy(true);
    let snapshot = initial;
    let title = "Завершить переучёт?";
    try {
      while (
        !snapshot.completed_at &&
        (await ask({ title, text: totals(snapshot), action: "Завершить" }))
      ) {
        try {
          await request("POST", `/stocktakes/${id}/complete`, { version: snapshot.version });
          setError("");
          await refresh();
          break;
        } catch (reason) {
          if (
            !(reason instanceof ApiError) ||
            (reason.detail as { code?: string })?.code !== "document_changed"
          )
            throw reason;
          const updated = await refresh();
          if (!updated) break;
          snapshot = updated;
          title = "Итог изменился. Завершить переучёт?";
        }
      }
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page count-page">
      <PageHead
        title={`Переучёт №${id}`}
        back={{ label: "Переучёты", onClick: () => go({ page: "stocktakes" }) }}
        meta={
          doc &&
          (doc.completed_at
            ? `Завершён ${formatDateTime(doc.completed_at)}${correcting ? " · Исправление" : ""}`
            : `Начат ${formatDateTime(doc.started_at)}`)
        }
      >
        {doc &&
          (doc.completed_at ? (
            <button
              className="button button-soft"
              disabled={busy || Boolean(form.pending) || (correcting && dirty)}
              onClick={() => {
                setCorrecting(!correcting);
                setError("");
              }}
            >
              {correcting ? "Закончить исправление" : "Исправить"}
            </button>
          ) : (
            <button
              className="button button-soft"
              disabled={busy || dirty}
              onClick={() => void complete(doc)}
            >
              Завершить переучёт
            </button>
          ))}
      </PageHead>
      {syncError && (
        <div className="alert count-feedback" role="status">
          {syncError}{" "}
          <button className="button button-ghost" onClick={refresh}>
            Обновить
          </button>
        </div>
      )}
      {storageError && (
        <p className="alert" role="alert">
          Браузер не смог сохранить ввод на устройстве. Оставьте вкладку открытой.
        </p>
      )}
      {error && (
        <p className="alert count-feedback" role="alert">
          {error}
        </p>
      )}
      {!doc && !syncError && <p role="status">Загружаем переучёт…</p>}
      {doc && (
        <>
          {(editable || dirty) && (
            <form
              className="sheet count-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (editable && !form.pending) {
                  void submit({ ...form, pending: "save", correction: correcting });
                }
              }}
            >
              <div className="count-form-head">
                <h2 className="section-title">
                  {form.lineId ? "Изменить позицию" : "Добавить позицию"}
                </h2>
                <label className="count-amount-toggle">
                  <input
                    type="checkbox"
                    checked={form.byAmount}
                    disabled={busy || Boolean(form.pending) || !editable}
                    onChange={(event) => fields({ byAmount: event.target.checked })}
                  />
                  Ввести общую сумму
                </label>
              </div>
              <fieldset
                className={form.byAmount ? "count-fields count-fields-amount" : "count-fields"}
                disabled={busy || Boolean(form.pending) || !editable}
              >
                <StocktakeName
                  doc={doc}
                  value={form.name}
                  editing={form.lineId}
                  input={nameInput}
                  onChange={(name) => fields({ name })}
                  onPick={(item) => {
                    if (item.current_line_id !== null) {
                      const line = doc.lines.find((line) => line.id === item.current_line_id);
                      if (line) void edit(line, "suggestion");
                      return;
                    }
                    fields({
                      name: item.name,
                      unit: item.unit,
                      price: item.price?.replace(".", ",") ?? "",
                      quantity: "",
                      enteredAmount: "",
                    });
                    requestAnimationFrame(() => balanceInput.current?.focus());
                  }}
                />
                <label className="field">
                  <span className="field-label">Единица</span>
                  <select
                    className="input"
                    value={form.unit}
                    onChange={(event) => fields({ unit: event.target.value as Unit })}
                  >
                    <option>шт</option>
                    <option>кг</option>
                  </select>
                </label>
                <label className="field">
                  <span className="field-label">Цена за {form.unit}, ₽</span>
                  <input
                    className="input"
                    id="stocktake-price"
                    inputMode="decimal"
                    required={!form.byAmount}
                    placeholder={form.byAmount ? "Необязательно" : undefined}
                    value={form.price}
                    pattern={moneyPattern}
                    title="Рубли и копейки"
                    onChange={(event) => fields({ price: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">
                    {form.byAmount ? "Общая сумма, ₽" : `Остаток, ${form.unit}`}
                  </span>
                  {form.byAmount ? (
                    <input
                      ref={balanceInput}
                      className="input"
                      id="stocktake-amount"
                      inputMode="decimal"
                      required
                      value={form.enteredAmount}
                      pattern={moneyPattern}
                      title="Рубли и копейки"
                      onChange={(event) => fields({ enteredAmount: event.target.value })}
                    />
                  ) : (
                    <input
                      ref={balanceInput}
                      className="input"
                      inputMode={form.unit === "шт" ? "numeric" : "decimal"}
                      required
                      value={form.quantity}
                      pattern={form.unit === "шт" ? "[0-9]{1,9}" : "[0-9]{1,9}([.,][0-9]{1,3})?"}
                      title={
                        form.unit === "шт"
                          ? "Целое количество штук"
                          : "Килограммы с точностью до грамма"
                      }
                      onChange={(event) => fields({ quantity: event.target.value })}
                    />
                  )}
                </label>
                <button
                  type="submit"
                  className="button button-primary"
                  disabled={!form.name.trim() || changed || Boolean(duplicate)}
                >
                  {form.lineId ? "Сохранить" : "Добавить"}
                </button>
              </fieldset>
              {form.byAmount && (
                <output className="count-calculated" htmlFor="stocktake-price stocktake-amount">
                  {calculatedQuantity !== null && (
                    <>Расчётный остаток: <strong>{calculatedQuantity} {form.unit}</strong></>
                  )}
                </output>
              )}
              {form.pending === "save" && (
                <div className="count-feedback" role="status">
                  {busy ? (
                    "Сохраняем…"
                  ) : (
                    <>
                      Сохранение не подтверждено.{" "}
                      <button
                        type="button"
                        className="button button-soft"
                        onClick={() => void submit(form)}
                      >
                        Повторить
                      </button>
                    </>
                  )}
                </div>
              )}
              {!form.pending && (
                <>
                  {(duplicate || duplicateId) && (
                    <div className="count-feedback">
                      {duplicate
                        ? stocktakeHint(duplicate, duplicate.quantity, duplicate.amount)
                        : "Уже в переучёте"}
                      {duplicate && editable && (
                        <button
                          type="button"
                          className="button button-soft"
                          disabled={busy}
                          onClick={() => void edit(duplicate, "suggestion")}
                        >
                          Изменить позицию
                        </button>
                      )}
                    </div>
                  )}
                  {changed && (
                    <div className="count-feedback" role="status">
                      {currentLine ? (
                        <>
                          Сохранено коллегой: {currentLine.name} · остаток{" "}
                          {stocktakeBalance(currentLine)}
                          {currentLine.price !== null && ` · ${formatMoney(currentLine.price)} ₽ / ${currentLine.unit}`}.
                          <button
                            type="button"
                            className="button button-soft"
                            onClick={() => loadLine(currentLine)}
                          >
                            Принять данные коллеги
                          </button>
                          <button
                            type="button"
                            className="button button-soft"
                            onClick={() => {
                              remember({
                                ...form,
                                version: currentLine.version,
                                requestId: requestId(),
                              });
                              setError("");
                            }}
                          >
                            Оставить мой ввод
                          </button>
                        </>
                      ) : (
                        <>
                          Коллега удалил строку.
                          <button
                            type="button"
                            className="button button-soft"
                            onClick={() => {
                              remember({
                                ...form,
                                lineId: null,
                                version: null,
                                requestId: requestId(),
                              });
                              setError("");
                            }}
                          >
                            Добавить как новую
                          </button>
                        </>
                      )}
                    </div>
                  )}
                  {!editable && dirty && (
                    <p role="status">
                      Переучёт завершён. Чтобы сохранить ввод, выберите «Исправить».
                    </p>
                  )}
                  {dirty && (
                    <div className="count-form-actions">
                      <button
                        type="button"
                        className="button button-ghost"
                        disabled={busy}
                        onClick={reset}
                      >
                        {form.lineId ? "Отмена" : "Очистить ввод"}
                      </button>
                    </div>
                  )}
                </>
              )}
            </form>
          )}
          <StocktakeLines
            lines={doc.lines}
            total={doc.total}
            query={lineQuery}
            onQueryChange={setLineQuery}
            editable={editable}
            busy={busy || Boolean(form.pending)}
            highlight={highlight}
            edit={edit}
            remove={remove}
            feedback={deleteError || pendingRemoval ? (
              <>
                {deleteError && <p className="alert" role="alert">{deleteError}</p>}
                {pendingRemoval && (
                  <div className="count-feedback" role="status">
                    {busy ? "Удаляем позицию…" : (
                      <>
                        Удаление {removalName ? `«${removalName}»` : "позиции"} не подтверждено.
                        <button type="button" className="button button-soft" onClick={() => void submit(form)}>
                          Повторить удаление
                        </button>
                      </>
                    )}
                  </div>
                )}
              </>
            ) : null}
          />
        </>
      )}
    </main>
  );
}
