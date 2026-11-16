import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import { test } from "node:test";

import { DraftAutosave } from "../src/draftAutosave.ts";

function draft(form = {}) {
  return {
    id: 1,
    form: {
      invoice_number: "42",
      invoice_date: "16-11-2026",
      supplier: { id: 1 },
      totals: { cost_total: "100", base_total: null },
      lines: [{
        line_no: 1,
        name: "Товар",
        quantity: "1",
        unit: "шт",
        vat_percent: null,
        cost_price_total: "100",
        product_id: 1,
        retail_price: 120,
        revalue_quantity: null,
      }],
      ...form,
    },
    ready: true,
    products_ready: false,
    issues: [],
  };
}

function setup(t, send = async (form) => draft(form)) {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 1000 });
  const calls = [];
  const editor = new DraftAutosave({
    draft: draft(),
    send: (form) => {
      calls.push(form);
      return send(form);
    },
  });
  t.after(() => editor.stop());
  return { editor, calls };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

test("an untouched draft is never saved", async (t) => {
  const { editor, calls } = setup(t);

  t.mock.timers.tick(10000);
  assert.equal(await editor.flush(), true);

  assert.equal(calls.length, 0);
  assert.equal(editor.getSnapshot().saved, false);
});

test("typing saves once, 700 ms after the last keystroke", async (t) => {
  const { editor, calls } = setup(t);

  editor.update((form) => ({ ...form, invoice_number: "1" }));
  t.mock.timers.tick(500);
  editor.update((form) => ({ ...form, invoice_number: "12" }));
  t.mock.timers.tick(699);
  await setImmediate();
  assert.equal(calls.length, 0);
  t.mock.timers.tick(1);
  await setImmediate();

  assert.deepEqual(calls.map((form) => form.invoice_number), ["12"]);
  assert.equal(editor.dirty, false);
  assert.equal(editor.getSnapshot().saved, true);
});

for (const [field, change, expected] of [
  ["supplier", () => ({ id: 2 }), { id: 2 }],
  ["invoice_date", () => "15-11-2026", "15-11-2026"],
  ["totals", () => ({ cost_total: "200", base_total: "180" }), { cost_total: "200", base_total: "180" }],
  ["lines", () => [], []],
]) {
  test(`a change to ${field} is saved automatically`, async (t) => {
    const { editor, calls } = setup(t);

    editor.update((form) => ({ ...form, [field]: change(form[field]) }));
    t.mock.timers.tick(700);
    await setImmediate();

    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0][field], expected);
    assert.equal(editor.dirty, false);
  });
}

test("all editable line fields and added lines are saved", async (t) => {
  const { editor, calls } = setup(t);
  const line = {
    line_no: 2,
    name: "Другой товар",
    quantity: "2.5",
    unit: "кг",
    vat_percent: "10",
    cost_price_total: "250",
    product_id: 2,
    retail_price: 150,
    revalue_quantity: "3",
  };

  editor.update((form) => ({ ...form, lines: [line, { ...line, line_no: 3 }] }));
  t.mock.timers.tick(700);
  await setImmediate();

  assert.deepEqual(calls[0].lines, [line, { ...line, line_no: 3 }]);
  assert.equal(editor.dirty, false);
});

test("a delayed response cannot overwrite newer edits or overlap saves", async (t) => {
  const pending = deferred();
  let first = true;
  const { editor, calls } = setup(t, (form) => {
    if (first) {
      first = false;
      return pending.promise;
    }
    return Promise.resolve(draft(form));
  });

  editor.update((form) => ({ ...form, invoice_number: "old" }));
  t.mock.timers.tick(700);
  await setImmediate();
  editor.update((form) => ({ ...form, invoice_number: "new" }));
  t.mock.timers.tick(700);
  await setImmediate();
  assert.equal(calls.length, 1);
  pending.resolve(draft({ invoice_number: "old" }));
  await setImmediate();
  assert.equal(editor.getSnapshot().form.invoice_number, "new");
  t.mock.timers.tick(0);
  await setImmediate();

  assert.deepEqual(calls.map((form) => form.invoice_number), ["old", "new"]);
  assert.equal(editor.getSnapshot().draft.form.invoice_number, "new");
  assert.equal(editor.dirty, false);
});

test("edits during a save still get a full debounce from the last edit", async (t) => {
  const pending = deferred();
  const { editor, calls } = setup(t, (form) => calls.length === 1
    ? pending.promise
    : Promise.resolve(draft(form)));

  editor.update((form) => ({ ...form, invoice_number: "old" }));
  t.mock.timers.tick(700);
  await setImmediate();
  editor.update((form) => ({ ...form, invoice_number: "new" }));
  pending.resolve(draft({ invoice_number: "old" }));
  await setImmediate();
  t.mock.timers.tick(699);
  await setImmediate();
  assert.equal(calls.length, 1);
  t.mock.timers.tick(1);
  await setImmediate();

  assert.deepEqual(calls.map((form) => form.invoice_number), ["old", "new"]);
});

test("server normalization updates the submitted form without another save", async (t) => {
  const { editor, calls } = setup(t, async () => draft({ invoice_number: "normalized" }));

  editor.update((form) => ({ ...form, invoice_number: "typed" }));
  assert.equal(await editor.flush(), true);
  t.mock.timers.tick(10000);
  await setImmediate();

  assert.equal(editor.getSnapshot().form.invoice_number, "normalized");
  assert.equal(calls.length, 1);
  assert.equal(editor.dirty, false);
});

test("navigation flushes pending input without waiting for the timer", async (t) => {
  const { editor, calls } = setup(t);

  editor.update((form) => ({ ...form, invoice_number: "new" }));
  const result = await editor.flush();

  assert.equal(result, true);
  assert.deepEqual(calls.map((form) => form.invoice_number), ["new"]);
  assert.equal(editor.dirty, false);
});

test("navigation waits for both the active save and later edits", async (t) => {
  const pending = deferred();
  const { editor, calls } = setup(t, (form) => calls.length === 1
    ? pending.promise
    : Promise.resolve(draft(form)));

  editor.update((form) => ({ ...form, invoice_number: "old" }));
  const result = editor.flush();
  await setImmediate();
  editor.update((form) => ({ ...form, invoice_number: "new" }));
  pending.resolve(draft({ invoice_number: "old" }));

  assert.equal(await result, true);
  assert.deepEqual(calls.map((form) => form.invoice_number), ["old", "new"]);
  assert.equal(editor.dirty, false);
});

test("failed saves keep the input, stop retrying and can be retried explicitly", async (t) => {
  const { editor, calls } = setup(t, async (form) => {
    if (calls.length === 1) throw new Error("Нет связи");
    return draft(form);
  });

  editor.update((form) => ({ ...form, invoice_number: "new" }));
  assert.equal(await editor.flush(), false);
  t.mock.timers.tick(10000);
  await setImmediate();
  assert.equal(calls.length, 1);
  assert.equal(editor.getSnapshot().form.invoice_number, "new");
  assert.equal(editor.getSnapshot().error, "Нет связи");
  assert.equal(editor.getSnapshot().saving, false);
  assert.equal(editor.dirty, true);

  assert.equal(await editor.flush(), true);
  assert.equal(calls.length, 2);
  assert.equal(editor.getSnapshot().error, null);
  assert.equal(editor.dirty, false);
});

test("new edits after a validation error restart autosaving", async (t) => {
  const { editor, calls } = setup(t, async (form) => {
    if (calls.length === 1) throw new Error("Неверная цена");
    return draft(form);
  });

  editor.update((form) => ({ ...form, invoice_number: "invalid" }));
  assert.equal(await editor.flush(), false);
  editor.update((form) => ({ ...form, invoice_number: "fixed" }));
  t.mock.timers.tick(700);
  await setImmediate();

  assert.deepEqual(calls.map((form) => form.invoice_number), ["invalid", "fixed"]);
  assert.equal(editor.getSnapshot().error, null);
  assert.equal(editor.dirty, false);
});

test("an error from an older input does not block saving its correction", async (t) => {
  const pending = deferred();
  const { editor, calls } = setup(t, (form) => calls.length === 1
    ? pending.promise
    : Promise.resolve(draft(form)));

  editor.update((form) => ({ ...form, invoice_number: "invalid" }));
  t.mock.timers.tick(700);
  await setImmediate();
  editor.update((form) => ({ ...form, invoice_number: "fixed" }));
  pending.reject(new Error("Неверное значение"));
  await setImmediate();
  t.mock.timers.tick(700);
  await setImmediate();

  assert.deepEqual(calls.map((form) => form.invoice_number), ["invalid", "fixed"]);
  assert.equal(editor.getSnapshot().error, null);
  assert.equal(editor.dirty, false);
});

test("reset cancels a pending save", async (t) => {
  const { editor, calls } = setup(t);

  editor.update((form) => ({ ...form, invoice_number: "new" }));
  editor.reset();
  t.mock.timers.tick(700);
  await setImmediate();

  assert.equal(calls.length, 0);
  assert.equal(editor.getSnapshot().form.invoice_number, "42");
  assert.equal(editor.dirty, false);
});

test("unmount cancels a pending save", async (t) => {
  const { editor, calls } = setup(t);

  editor.update((form) => ({ ...form, invoice_number: "new" }));
  editor.stop();
  t.mock.timers.tick(700);
  await setImmediate();

  assert.equal(calls.length, 0);
});
