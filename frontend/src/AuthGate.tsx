import { useEffect, useState } from "react";

import App from "./App";
import { getMe, onSessionLost } from "./api";
import LoginPage from "./pages/LoginPage";
import type { Store } from "./stores";
import type { UserSummary } from "./types";

// lost: the session ended during the work, the app stays in memory behind the form
type Status = "checking" | "signed-out" | "signed-in" | "lost";

export default function AuthGate({ store }: { store: Store }) {
  const [status, setStatus] = useState<Status>("checking");
  const [user, setUser] = useState<UserSummary | null>(null);

  function signedIn(next: UserSummary) {
    setUser(next);
    setStatus("signed-in");
  }

  useEffect(() => {
    const unsubscribe = onSessionLost(() =>
      setStatus((current) => (current === "signed-in" ? "lost" : current)),
    );
    let current = true;
    getMe()
      .then((next) => current && signedIn(next))
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

  if (status === "signed-out" || !user) {
    return <LoginPage lost={false} onSignedIn={signedIn} />;
  }

  return (
    <>
      {status === "lost" && <LoginPage lost onSignedIn={signedIn} />}
      {/* unmounting would lose the unsaved draft and the photos of a batch */}
      <div className={status === "lost" ? "app-hidden" : "app-visible"}>
        <App key={user.id} userId={user.id} store={store} onSignedOut={() => setStatus("signed-out")} />
      </div>
    </>
  );
}
