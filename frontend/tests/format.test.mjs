import assert from "node:assert/strict";
import { test } from "node:test";

import { formatMoney, formatQuantityFromAmount, formatSignedKopecks, revaluationKopecks } from "../src/format.ts";

test("revaluations round each product to the nearest kopeck before summing", () => {
  const first = revaluationKopecks("0.5", "95.49", "95.50");
  const second = revaluationKopecks("0.5", "12.00", "12.01");
  assert.equal(first + second, 2n);
  assert.equal(formatSignedKopecks(first + second), "+0,02");
  assert.equal(formatSignedKopecks(revaluationKopecks("0.5", "95.50", "95.49")), "−0,01");
  assert.equal(formatSignedKopecks(revaluationKopecks("0.499", "95.50", "95.49")), "0,00");
  assert.equal(revaluationKopecks("0,", "95.50", "95.49"), null);
});

test("large stocktake totals retain their kopecks", () => {
  assert.equal(formatMoney("9007199254740993.01").replace(/\s/g, ""), "9007199254740993,01");
});

test("the balance is the entered amount divided by the unit price", () => {
  assert.equal(formatQuantityFromAmount("1200", "240.00"), "5");
  assert.equal(formatQuantityFromAmount("548,37", "365,58"), "1,5");
  assert.equal(formatQuantityFromAmount("0", "19.90"), "0");
  const largeQuantity = formatQuantityFromAmount("999999999999.99", "0.02");
  assert.equal(largeQuantity.replace(/\s/g, ""), "49999999999999,5");
});

test("rounded quantities are marked and positive balances below display precision remain visible", () => {
  assert.equal(formatQuantityFromAmount("10", "6"), "≈ 1,667");
  assert.equal(formatQuantityFromAmount("1", "16"), "≈ 0,063");
  assert.equal(formatQuantityFromAmount("0.01", "1000"), "< 0,001");
});

test("incomplete input and a missing or zero unit price leave the calculated balance empty", () => {
  for (const [amount, price] of [
    ["", "10"],
    ["1,", "10"],
    ["-1", "10"],
    ["10", ""],
    ["10", null],
    ["10", "0,00"],
  ]) {
    assert.equal(formatQuantityFromAmount(amount, price), null);
  }
});
