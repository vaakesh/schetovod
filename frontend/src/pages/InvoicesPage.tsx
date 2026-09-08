import { useEffect, useState } from "react";

import { listInvoices } from "../api";
import UploadForm, { type UploadKind } from "../components/UploadForm";
import { formatDate, formatMoney, formatText } from "../format";
import { message } from "../message";
import type { Route } from "../router";
import type { InvoiceListItem, InvoiceStatus } from "../types";

interface Props {
  go: (route: Route) => void;
  uploadJson: (files: File[]) => void;
  uploadImages: (files: File[]) => void;
  uploading: UploadKind | null;
  notice: string | null;
}

const PAGE = 50;

const FILTERS: { status: InvoiceStatus | null; label: string }[] = [
  { status: null, label: "Все" },
  { status: "draft", label: "Черновики" },
  { status: "confirmed", label: "Проведённые" },
  { status: "declined", label: "Отклонённые" },
];

const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Черновик",
  confirmed: "Проведена",
  declined: "Отклонена",
};

// a declined upload has nothing to open
function target(item: InvoiceListItem): Route | null {
  if (item.status === "draft") {
    return { page: "draft", id: item.id };
  }
  if (item.status === "confirmed") {
    return { page: "posted", id: item.id };
  }
  return null;
}

export default function InvoicesPage({ go, uploadJson, uploadImages, uploading, notice }: Props) {
  const [status, setStatus] = useState<InvoiceStatus | null>(null);
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<InvoiceListItem[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = search.trim();

  // the search waits for a pause in typing, a late answer to an old query is dropped
  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(
      () => {
        listInvoices({ status, q: query, limit: PAGE, offset: 0 })
          .then((page) => {
            if (current) {
              setItems(page.items);
              setHasMore(page.has_more);
              setError(null);
            }
          })
          .catch((reason) => current && setError(message(reason)));
      },
      query ? 250 : 0,
    );
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [status, query]);

  async function more() {
    if (!items) {
      return;
    }
    setLoadingMore(true);
    try {
      const page = await listInvoices({ status, q: query, limit: PAGE, offset: items.length });
      setItems([...items, ...page.items]);
      setHasMore(page.has_more);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  function uploads(slim: boolean) {
    return (
      <div className={slim ? "upload-grid upload-grid-slim" : "upload-grid"}>
        <UploadForm kind="json" slim={slim} uploading={uploading} onFiles={uploadJson} />
        <UploadForm kind="image" slim={slim} uploading={uploading} onFiles={uploadImages} />
      </div>
    );
  }

  // nothing uploaded yet, the page is only the drop areas
  if (items !== null && items.length === 0 && status === null && !query && !error) {
    return (
      <main className="page page-empty">
        {notice && <p className="hero-notice">{notice}</p>}
        <h1 className="hero-title">Загрузите накладную</h1>
        {uploads(false)}
      </main>
    );
  }

  return (
    <main className="page">
      {notice && <p className="page-notice">{notice}</p>}
      {uploads(true)}

      <div className="list-head">
        <div className="segments" role="tablist">
          {FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              role="tab"
              aria-selected={status === filter.status}
              className={status === filter.status ? "segment active" : "segment"}
              onClick={() => setStatus(filter.status)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <input
          className="input search"
          type="search"
          placeholder="Продавец или номер"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      <section className="sheet">
        <div className="table-wrap">
          <table className="list">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Номер</th>
                <th>Продавец</th>
                <th className="num">Строк</th>
                <th className="num">В рознице</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {items?.map((item) => {
                const route = target(item);
                return (
                  <tr
                    key={item.id}
                    className={route ? "list-row clickable" : "list-row muted-row"}
                    tabIndex={route ? 0 : undefined}
                    onClick={() => route && go(route)}
                    onKeyDown={(event) => {
                      if (route && event.key === "Enter") {
                        go(route);
                      }
                    }}
                  >
                    <td className="nowrap">{formatDate(item.invoice_date)}</td>
                    <td className="nowrap">{formatText(item.invoice_number)}</td>
                    <td className="list-supplier">{formatText(item.supplier_name)}</td>
                    <td className="num muted-cell">{item.lines}</td>
                    <td className="num strong">
                      {item.retail_total === null ? "" : `${formatMoney(item.retail_total)} ₽`}
                    </td>
                    <td>
                      <span className={`status-dot status-${item.status}`}>
                        {STATUS_LABELS[item.status]}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {items?.length === 0 && <p className="list-empty">Ничего не найдено</p>}
      </section>

      {hasMore && (
        <div className="more">
          <button type="button" className="button button-ghost" disabled={loadingMore} onClick={more}>
            Показать ещё
          </button>
        </div>
      )}
    </main>
  );
}
