import { useState } from "react";

import { login } from "../api";
import Icon from "../components/icons";
import { message } from "../message";

interface Props {
  // the session ended during the work, the form says that nothing is lost
  lost: boolean;
  onSignedIn: () => void;
}

export default function LoginPage({ lost, onSignedIn }: Props) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const valid = name.trim() !== "" && password !== "";

  async function submit() {
    if (!valid || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login({ login: name, password });
      onSignedIn();
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form
        className="login-card"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="brand" size={16} />
          </span>
          <span className="brand-name">Счетовод</span>
        </div>
        <h1 className="login-title">Вход</h1>
        {lost && (
          <p className="login-text">Сессия закончилась. Войдите снова, открытая работа сохранена.</p>
        )}
        <div className="fields">
          <label className="field">
            <span className="field-label">Логин</span>
            <input
              className="input"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoFocus
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Пароль</span>
            <input
              className="input"
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        </div>
        {error && <pre className="modal-error">{error}</pre>}
        <button
          type="submit"
          className="button button-primary login-submit"
          disabled={!valid || busy}
        >
          Войти
        </button>
      </form>
    </main>
  );
}
