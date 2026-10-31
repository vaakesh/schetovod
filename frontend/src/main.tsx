import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import AuthGate from "./AuthGate";
import "./styles.css";

// Safari on iPad applies :active only when a touch listener exists
document.addEventListener("touchstart", () => undefined, { passive: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate />
  </StrictMode>,
);
