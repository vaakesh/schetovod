import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import { test } from "node:test";

import { watchStocktake } from "../src/stocktakeEvents.ts";

function replaceGlobal(t, key, value) {
  const original = Object.getOwnPropertyDescriptor(globalThis, key);
  Object.defineProperty(globalThis, key, { value, configurable: true });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, key, original);
    else delete globalThis[key];
  });
}

function setup(t, initialRead = async () => 1) {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let stop;
  t.after(() => stop?.());
  const sockets = [];
  class Socket {
    constructor() { sockets.push(this); }
    emit(event) { this.onmessage({ data: JSON.stringify(event) }); }
    close(code = 1000) { this.onclose({ code }); }
  }
  const network = { onLine: true };
  const browser = Object.assign(new EventTarget(), { setTimeout, clearTimeout });
  replaceGlobal(t, "WebSocket", Socket);
  replaceGlobal(t, "navigator", network);
  replaceGlobal(t, "window", browser);
  replaceGlobal(t, "document", new EventTarget());
  let version = 0;
  const reads = [];
  const server = { read: initialRead, sessions: 0 };
  stop = watchStocktake({
    url: new URL("ws://localhost/events"),
    currentVersion: () => version,
    refresh: async () => {
      reads.push(version);
      version = Math.max(version, await server.read());
      return { version };
    },
    ensureSession: async () => { server.sessions++; },
    setDisconnected: () => {},
  });
  return { reads, sockets, server, browser, network, stop };
}

test("a commit during the ready check is fetched, repeated and older versions are ignored", async (t) => {
  const { reads, sockets, server } = setup(t);
  await setImmediate();
  const [socket] = sockets;
  const pending = Promise.withResolvers();
  server.read = () => pending.promise;
  socket.emit({ type: "ready" });
  socket.emit({ type: "changed", version: 2 });
  socket.emit({ type: "changed", version: 3 });
  assert.deepEqual(reads, [0, 1]);

  server.read = async () => 3;
  pending.resolve(1);
  await setImmediate();
  socket.emit({ type: "changed", version: 3 });
  socket.emit({ type: "changed", version: 2 });
  t.mock.timers.tick(60000);
  assert.deepEqual(reads, [0, 1, 1]);
  assert.equal(sockets.length, 1);
});

test("reconnecting catches up once and leaving cancels a scheduled reconnect", async (t) => {
  const { reads, sockets, server, browser, network, stop } = setup(t);
  await setImmediate();
  const [first] = sockets;
  first.emit({ type: "ready" });
  await setImmediate();

  network.onLine = false;
  browser.dispatchEvent(new Event("offline"));
  t.mock.timers.tick(60000);
  server.read = async () => 7;
  network.onLine = true;
  browser.dispatchEvent(new Event("online"));
  const second = sockets[1];
  second.emit({ type: "ready" });
  await setImmediate();
  first.emit({ type: "changed", version: 99 });
  second.emit({ type: "changed", version: 7 });
  assert.deepEqual(reads, [0, 1, 1]);

  second.close();
  t.mock.timers.tick(999);
  assert.equal(sockets.length, 2);
  t.mock.timers.tick(1);
  assert.equal(sockets.length, 3);
  sockets[2].emit({ type: "ready" });
  await setImmediate();
  sockets[2].close();
  stop();
  t.mock.timers.tick(60000);
  assert.equal(sockets.length, 3);
});

test("a page restored from cache checks its version and renews an expired socket session over HTTP", async (t) => {
  const pending = Promise.withResolvers();
  const { reads, sockets, server, browser } = setup(t, () => pending.promise);
  browser.dispatchEvent(new Event("pagehide"));
  pending.resolve(4);
  await setImmediate();
  assert.equal(sockets.length, 0);

  browser.dispatchEvent(new Event("pageshow"));
  sockets[0].emit({ type: "ready" });
  await setImmediate();
  sockets[0].close(4401);
  await setImmediate();
  assert.equal(server.sessions, 1);
  assert.deepEqual(reads, [0, 4]);
  t.mock.timers.tick(1000);
  sockets[1].emit({ type: "ready" });
  await setImmediate();
  assert.deepEqual(reads, [0, 4, 4]);
});
