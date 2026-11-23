import { useCallback, useEffect, useRef, useState } from "react";

import { request } from "../api";
import PageHead from "../components/PageHead";
import { formatDateTime, formatMoney } from "../format";
import { message } from "../message";
import { isPlainLinkClick, routeHash, type Route } from "../router";
import { lineCount, requestId, type CountSummary } from "../stocktakes";
import "../stocktakes.css";

export default function StocktakesPage({ go }: { go: (route: Route) => void }) {
  const [items, setItems] = useState<CountSummary[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const token = useRef(requestId());
  const load = useCallback(async () => {
    try {
      setItems(await request<CountSummary[]>("GET", "/stocktakes"));
      setError("");
    } catch (reason) {
      setError(message(reason));
    }
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  async function open() {
    setBusy(true);
    try {
      const result = await request<{ document_id: number }>("POST", "/stocktakes/open", {
        request_id: token.current,
      });
      go({ page: "stocktake", id: result.document_id });
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  const current = items?.find((item) => !item.completed_at);
  const history = items?.filter((item) => item.completed_at) ?? [];
  return (
    <main className="page count-page">
      <PageHead title="Переучёты" />
      {error && (
        <div className="alert" role="alert">
          {error}{" "}
          <button className="button button-ghost" onClick={load}>
            Обновить
          </button>
        </div>
      )}
      {items ? (
        <>
          <section className="sheet count-overview">
            <div>
              <h2 className="section-title">
                {current ? `Текущий переучёт №${current.id}` : "Новый переучёт"}
              </h2>
              <p className="page-head-meta">
                {current
                  ? `Начат ${formatDateTime(current.started_at)} · ${lineCount(current.line_count)} · ${formatMoney(current.total)} ₽`
                  : "Открытого переучёта пока нет"}
              </p>
            </div>
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => (current ? go({ page: "stocktake", id: current.id }) : void open())}
            >
              {current ? "Продолжить переучёт" : "Начать переучёт"}
            </button>
          </section>
          <div className="section-head">
            <h2 className="section-title" id="stocktake-history">История переучётов</h2>
          </div>
          <section className="sheet" aria-labelledby="stocktake-history">
            {history.length ? (
              history.map((item) => (
                <a
                  className="count-history-row"
                  key={item.id}
                  href={routeHash({ page: "stocktake", id: item.id })}
                  onClick={(event) => {
                    if (isPlainLinkClick(event)) {
                      event.preventDefault();
                      go({ page: "stocktake", id: item.id });
                    }
                  }}
                >
                  <span>
                    <strong>Переучёт №{item.id}</strong>
                    <small>{formatDateTime(item.completed_at!)}</small>
                  </span>
                  <span>{lineCount(item.line_count)}</span>
                  <strong>{formatMoney(item.total)} ₽</strong>
                </a>
              ))
            ) : (
              <p className="list-empty">Завершённых переучётов пока нет</p>
            )}
          </section>
        </>
      ) : (
        !error && <p role="status">Загружаем переучёты…</p>
      )}
    </main>
  );
}
