import { useEffect, useState } from "react";

import App from "./App";
import { getMe, onSessionLost } from "./api";
import LoginPage from "./pages/LoginPage";

// lost: the session ended during the work, the app stays in memory behind the form
type Status = "checking" | "signed-out" | "signed-in" | "lost";

export default function AuthGate() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const unsubscribe = onSessionLost(() =>
      setStatus((current) => (current === "signed-in" ? "lost" : current)),
    );
    let current = true;
    getMe()
      .then(() => current && setStatus("signed-in"))
      .catch(() => current && setStatus("signed-out"));
    return () => {
      current = false;
      unsubscribe();
    };
  }, []);

  if (status === "checking") {
    return (
      <div className="login">
        <span className="spinner" role="status" aria-label="Проверяем вход" />
      </div>
    );
  }

  if (status === "signed-out") {
    return <LoginPage lost={false} onSignedIn={() => setStatus("signed-in")} />;
  }

  return (
    <>
      {status === "lost" && <LoginPage lost onSignedIn={() => setStatus("signed-in")} />}
      {/* unmounting would lose the unsaved draft and the photos of a batch */}
      <div className={status === "lost" ? "app-hidden" : "app-visible"}>
        <App onSignedOut={() => setStatus("signed-out")} />
      </div>
    </>
  );
}
