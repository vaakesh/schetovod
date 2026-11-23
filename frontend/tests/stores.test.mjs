import assert from "node:assert/strict";
import { test } from "node:test";

import { isPlainLinkClick, parseRoute, routeAvailable, routeHash, storeSwitchRoute } from "../src/router.ts";
import { apiPath, resolveStore, storePath } from "../src/stores.ts";

test("store URLs keep the legacy root and resolve the canonical store paths", () => {
  assert.equal(resolveStore("/"), "gastronom");
  assert.equal(resolveStore("/gastronom"), "gastronom");
  assert.equal(resolveStore("/meat"), "meat");
  assert.equal(resolveStore("/unknown/"), null);
  assert.equal(resolveStore("/meat/ledger"), null);

  for (const store of ["gastronom", "meat"]) {
    assert.equal(resolveStore(storePath(store)), store);
  }
});

test("store data and downloads use the URL of the current store and auth stays shared", () => {
  for (const store of ["gastronom", "meat"]) {
    for (const path of ["/ledger?limit=50", "/invoice/1", "/ledger/report.pdf", "/invoices/print.pdf"]) {
      assert.equal(apiPath(store, path), `/api/stores/${store}${path}`);
    }
    assert.equal(apiPath(store, "/auth/me"), "/api/auth/me");
    assert.equal(apiPath(store, "/auth/refresh"), "/api/auth/refresh");
  }
});

test("orders and analytics are unavailable from direct links in the meat store", () => {
  for (const hash of ["#/orders", "#/traffic", "#/profit", "#/purchases", "#/stocktakes", "#/stocktakes/12"]) {
    const { page } = parseRoute(hash);
    assert.equal(routeAvailable("gastronom", page), true);
    assert.equal(routeAvailable("meat", page), false);
  }
  for (const hash of ["#/ledger", "#/report", "#/catalog", "#/price-tags"]) {
    assert.equal(routeAvailable("meat", parseRoute(hash).page), true);
  }
});

test("the store switch preserves shared sections and leaves store-specific pages behind", () => {
  for (const hash of ["#/", "#/upload", "#/catalog", "#/ledger", "#/report", "#/price-tags/base"]) {
    assert.equal(routeHash(storeSwitchRoute("meat", parseRoute(hash))), hash);
    assert.equal(routeHash(storeSwitchRoute("gastronom", parseRoute(hash))), hash);
  }
  for (const hash of ["#/invoice/1", "#/posted/1", "#/orders", "#/traffic", "#/profit", "#/purchases"]) {
    assert.equal(routeHash(storeSwitchRoute("meat", parseRoute(hash))), "#/");
  }
  for (const hash of ["#/invoice/1", "#/posted/1"]) {
    assert.equal(routeHash(storeSwitchRoute("gastronom", parseRoute(hash))), "#/");
  }
});

test("modified link clicks keep their native browser behavior", () => {
  assert.equal(isPlainLinkClick({ button: 0 }), true);
  for (const modifier of ["altKey", "ctrlKey", "metaKey", "shiftKey", "defaultPrevented"]) {
    assert.equal(isPlainLinkClick({ button: 0, [modifier]: true }), false);
  }
  assert.equal(isPlainLinkClick({ button: 1 }), false);
});
