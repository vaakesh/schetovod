import { useCallback, useEffect, useRef, useState } from "react";

import { getDraftOrder, logout, receiveInvoice, recognizeInvoice } from "./api";
import { useBatchUpload, type BatchUpload } from "./batch";
import { useConfirm } from "./components/ConfirmDialog";
import Icon from "./components/icons";
import Sidebar from "./components/Sidebar";
import { UPLOAD_LOADING, type UploadKind } from "./components/UploadMenu";
import { message } from "./message";
import CatalogPage from "./pages/CatalogPage";
import DraftPage from "./pages/DraftPage";
import InvoicesPage from "./pages/InvoicesPage";
import LedgerPage from "./pages/LedgerPage";
import OrdersPage from "./pages/OrdersPage";
import PostedInvoicePage from "./pages/PostedInvoicePage";
import ReportPage from "./pages/ReportPage";
import TrafficPage from "./pages/TrafficPage";
import UploadPage from "./pages/UploadPage";
import { routeHash, sameRoute, useRoute, useRouteMotion, type Route } from "./router";
import type { InvoiceDraft, Order } from "./types";

type Guard = () => Promise<boolean>;

function batchStatus({ running, done, failed, total }: BatchUpload): string {
  if (running) {
    return `Распознаём накладные: готово ${done} из ${total}`;
  }
  return failed > 0
    ? `Накладные распознаны: готово ${done} из ${total}, с ошибкой ${failed}`
    : `Накладные распознаны: готово ${done} из ${total}`;
}

interface Props {
  onSignedOut: () => void;
}

export default function App({ onSignedOut }: Props) {
  const route = useRoute();
  const motion = useRouteMotion(route);
  const [ask, confirmDialog] = useConfirm();
  // a page with unsaved edits asks before it is left
  const guard = useRef<Guard | null>(null);
  const [uploaded, setUploaded] = useState<InvoiceDraft | null>(null);
  const [uploading, setUploading] = useState<UploadKind | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // the order being filled, null when it is empty, undefined until it is loaded
  const [cart, setCart] = useState<Order | null | undefined>(undefined);
  // kept here so that the queue goes on while other pages are open
  const batch = useBatchUpload();
  // the results of a batch are announced until the upload page is opened
  const [batchUnseen, setBatchUnseen] = useState(false);

  useEffect(() => {
    if (batch.running) {
      setBatchUnseen(true);
    } else if (route.page === "upload") {
      setBatchUnseen(false);
    }
  }, [batch.running, route.page]);

  // the photos live only in this tab
  useEffect(() => {
    if (!batch.running) {
      return;
    }
    function onLeave(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [batch.running]);

  // read again on every page, another tab may have changed it
  useEffect(() => {
    let current = true;
    getDraftOrder()
      .then((next) => current && setCart(next))
      // the tab counter is a hint, the orders page shows the error itself
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [route.page]);

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

  async function signOut() {
    if (!(await leave())) {
      return;
    }
    try {
      await logout();
      onSignedOut();
    } catch (error) {
      setUploadError(message(error));
    }
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
            onProductsAdded={({ created, skipped }) =>
              void go(
                { page: "invoices" },
                `Добавлено товаров: ${created}, уже были в каталоге: ${skipped}`,
              )
            }
          />
        );
      case "posted":
        return <PostedInvoicePage key={route.id} id={route.id} go={go} />;
      case "catalog":
        return <CatalogPage ask={ask} go={go} cart={cart ?? null} onCart={setCart} />;
      case "orders":
        return <OrdersPage ask={ask} go={go} cart={cart} onCart={setCart} />;
      case "ledger":
        return <LedgerPage go={go} ask={ask} />;
      case "report":
        return <ReportPage go={go} />;
      case "traffic":
        return <TrafficPage />;
      case "upload":
        return <UploadPage batch={batch} go={go} />;
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
    <div className="shell">
      <Sidebar
        route={route}
        cart={cart}
        uploading={uploading !== null}
        working={uploading !== null || batch.running}
        go={(next) => void go(next)}
        signOut={() => void signOut()}
      />
      <div className="shell-main">
        {/* recognition takes minutes, the user may leave the invoices meanwhile */}
        {uploading && (
          <div className="upload-status" role="status">
            <span className="spinner" />
            {UPLOAD_LOADING[uploading]}
          </div>
        )}
        {batchUnseen && route.page !== "upload" && (
          <button
            type="button"
            className="upload-status upload-status-link"
            aria-live="polite"
            onClick={() => void go({ page: "upload" })}
          >
            {batch.running ? <span className="spinner" /> : <Icon name="check" size={18} />}
            {batchStatus(batch)}
          </button>
        )}
        {uploadError && (
          <div className="page-alert">
            <div className="alert">
              <pre>{uploadError}</pre>
            </div>
          </div>
        )}
        {/* the key replays the entrance on every page, also between two invoices */}
        <div key={routeHash(route)} className={`route-view route-${motion}`}>
          {page()}
        </div>
      </div>
      {confirmDialog}
    </div>
  );
}
