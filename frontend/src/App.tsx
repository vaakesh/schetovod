import { useCallback, useRef, useState } from "react";

import { receiveInvoice, recognizeInvoice } from "./api";
import { useConfirm } from "./components/ConfirmDialog";
import UploadForm, { type UploadKind } from "./components/UploadForm";
import { message } from "./message";
import CatalogPage from "./pages/CatalogPage";
import DraftPage from "./pages/DraftPage";
import InvoicesPage from "./pages/InvoicesPage";
import LedgerPage from "./pages/LedgerPage";
import PostedInvoicePage from "./pages/PostedInvoicePage";
import ReportPage from "./pages/ReportPage";
import { routeHash, sameRoute, useRoute, type Route } from "./router";
import type { InvoiceDraft } from "./types";

type Guard = () => Promise<boolean>;

export default function App() {
  const route = useRoute();
  const [ask, confirmDialog] = useConfirm();
  // a page with unsaved edits asks before it is left
  const guard = useRef<Guard | null>(null);
  const [uploaded, setUploaded] = useState<InvoiceDraft | null>(null);
  const [uploading, setUploading] = useState<UploadKind | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const setGuard = useCallback((next: Guard | null) => {
    guard.current = next;
  }, []);

  async function leave(): Promise<boolean> {
    if (guard.current && !(await guard.current())) {
      return false;
    }
    guard.current = null;
    return true;
  }

  async function go(next: Route, nextNotice: string | null = null) {
    if (sameRoute(next, route) || !(await leave())) {
      return;
    }
    setNotice(nextNotice);
    setUploadError(null);
    window.location.hash = routeHash(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  async function upload(kind: UploadKind, send: () => Promise<InvoiceDraft>) {
    if (!(await leave())) {
      return;
    }
    setUploadError(null);
    setNotice(null);
    setUploading(kind);
    try {
      const draft = await send();
      setUploaded(draft);
      window.location.hash = routeHash({ page: "draft", id: draft.id });
    } catch (error) {
      setUploadError(message(error));
    } finally {
      setUploading(null);
    }
  }

  function uploadJson(files: File[]) {
    void upload("json", async () => {
      let body: unknown;
      try {
        body = JSON.parse(await files[0]!.text());
      } catch {
        throw new Error("Файл не JSON");
      }
      return receiveInvoice(body);
    });
  }

  function uploadImages(files: File[]) {
    void upload("image", () => recognizeInvoice(files));
  }

  function tab(target: Route, label: string, active: boolean) {
    return (
      <a
        href={routeHash(target)}
        className={active ? "tab active" : "tab"}
        aria-current={active ? "page" : undefined}
        onClick={(event) => {
          event.preventDefault();
          void go(target);
        }}
      >
        {label}
      </a>
    );
  }

  function page() {
    switch (route.page) {
      case "draft":
        return (
          <DraftPage
            key={route.id}
            id={route.id}
            initial={uploaded}
            ask={ask}
            setGuard={setGuard}
            onHome={() => void go({ page: "invoices" })}
            onDeclined={(id) => void go({ page: "invoices" }, `Черновик №${id} отклонён`)}
          />
        );
      case "posted":
        return <PostedInvoicePage key={route.id} id={route.id} go={go} />;
      case "catalog":
        return <CatalogPage />;
      case "ledger":
        return <LedgerPage go={go} ask={ask} />;
      case "report":
        return <ReportPage go={go} />;
      case "invoices":
        return (
          <InvoicesPage
            go={go}
            uploadJson={uploadJson}
            uploadImages={uploadImages}
            uploading={uploading}
            notice={notice}
          />
        );
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-start">
          <button
            type="button"
            className="brand"
            aria-label="Счетовод — на главную"
            title="На главную"
            disabled={uploading !== null}
            onClick={() => void go({ page: "invoices" })}
          >
            <span className="brand-mark" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24">
                <path
                  d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            Счетовод
          </button>
          <nav className="tabs">
            {tab(
              { page: "invoices" },
              "Накладные",
              route.page !== "catalog" && route.page !== "ledger" && route.page !== "report",
            )}
            {tab({ page: "catalog" }, "Товары", route.page === "catalog")}
            {tab({ page: "ledger" }, "Журнал", route.page === "ledger")}
            {tab({ page: "report" }, "Отчёт", route.page === "report")}
          </nav>
        </div>
        {route.page !== "invoices" && (
          <div className="topbar-upload">
            <UploadForm compact kind="json" uploading={uploading} onFiles={uploadJson} />
            <UploadForm compact kind="image" uploading={uploading} onFiles={uploadImages} />
          </div>
        )}
      </header>

      {uploadError && (
        <div className="page-alert">
          <div className="alert">
            <pre>{uploadError}</pre>
          </div>
        </div>
      )}

      {page()}
      {confirmDialog}
    </div>
  );
}
