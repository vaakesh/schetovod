import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import AuthGate from "./AuthGate";
import { resolveStore, STORE_NAMES, storePath } from "./stores";
import "./styles.css";

const { pathname, search, hash } = window.location;
const store = resolveStore(pathname);
if (store !== null) {
  const canonicalPath = storePath(store);
  if (pathname !== canonicalPath) {
    window.history.replaceState(null, "", `${canonicalPath}${search}${hash}`);
  }
  document.title = `${STORE_NAMES[store]} · Счетовод`;
}

// Safari on iPad applies :active only when a touch listener exists
document.addEventListener("touchstart", () => undefined, { passive: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {store === null ? (
      <main className="page page-empty">
        <h1 className="hero-title">Страница не найдена</h1>
        <a href={storePath("gastronom")}>Открыть Гастроном</a>
      </main>
    ) : (
      <AuthGate store={store} />
    )}
  </StrictMode>,
);
