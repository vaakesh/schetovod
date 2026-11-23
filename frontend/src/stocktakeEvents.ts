interface Subscription {
  url: URL;
  currentVersion: () => number;
  refresh: () => Promise<{ version: number } | null>;
  ensureSession: () => Promise<void>;
  setDisconnected: (disconnected: boolean) => void;
}

export function watchStocktake({
  url,
  currentVersion,
  refresh,
  ensureSession,
  setDisconnected,
}: Subscription) {
  let socket: WebSocket | null = null;
  let retry: number | undefined;
  let delay = 1000;
  let stopped = false;
  let suspended = false;

  function connect() {
    window.clearTimeout(retry);
    if (stopped || suspended || socket || !navigator.onLine) return;
    const connection = new WebSocket(url);
    socket = connection;
    let ready = false;
    let loading = false;
    let targetVersion = 0;

    async function synchronize() {
      if (loading) return;
      loading = true;
      do {
        const expected = targetVersion;
        const updated = await refresh();
        if (socket !== connection) return;
        if (!updated || updated.version < expected) {
          connection.close();
          return;
        }
        // a newer commit can arrive while its predecessor is being fetched
      } while (currentVersion() < targetVersion);
      loading = false;
      delay = 1000;
      setDisconnected(false);
    }

    connection.onmessage = ({ data }) => {
      if (socket !== connection) return;
      const event = JSON.parse(data);
      if (event.type === "ready") {
        ready = true;
        void synchronize();
      } else if (event.type === "changed" && event.version > currentVersion()) {
        targetVersion = Math.max(targetVersion, event.version);
        void synchronize();
      }
    };
    connection.onclose = async ({ code }) => {
      if (socket !== connection) return;
      socket = null;
      setDisconnected(true);
      // a rejected handshake or expired access cookie can be renewed over HTTP
      if ((!ready || code === 4401) && navigator.onLine) {
        try {
          await ensureSession();
        } catch {
          // the next handshake retries after the network or the user session recovers
        }
      }
      if (stopped || suspended || socket || !navigator.onLine) return;
      retry = window.setTimeout(connect, delay);
      delay = Math.min(delay * 2, 30000);
    };
  }

  function disconnect() {
    window.clearTimeout(retry);
    const connection = socket;
    socket = null;
    connection?.close();
  }
  function offline() {
    disconnect();
    setDisconnected(true);
  }
  function hidePage() {
    suspended = true;
    disconnect();
  }
  function showPage() {
    suspended = false;
    connect();
  }
  function visible() {
    if (document.hidden || !navigator.onLine) return;
    if (!socket) connect();
    else if (socket.readyState === WebSocket.OPEN) void refresh();
  }

  window.addEventListener("online", connect);
  window.addEventListener("offline", offline);
  window.addEventListener("pagehide", hidePage);
  window.addEventListener("pageshow", showPage);
  document.addEventListener("visibilitychange", visible);
  // load the document even if a proxy is blocking the websocket upgrade
  void refresh().then(connect);
  return () => {
    stopped = true;
    disconnect();
    window.removeEventListener("online", connect);
    window.removeEventListener("offline", offline);
    window.removeEventListener("pagehide", hidePage);
    window.removeEventListener("pageshow", showPage);
    document.removeEventListener("visibilitychange", visible);
  };
}
