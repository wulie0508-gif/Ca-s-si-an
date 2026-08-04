"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");

const calculator = require(path.resolve(
  __dirname,
  "../../public-preview/valuation-calculator.js",
));

function defaultInput(overrides = {}) {
  return {
    currency: "CNY",
    unit: "million",
    fcff: [4.2, 6.3, 8.9, 11.8, 14.6],
    waccPct: 11.5,
    terminalGrowthPct: 2.5,
    discountConvention: "period_end",
    cash: 12,
    debt: 24.5,
    otherClaims: 1.5,
    dilutedShares: 18,
    comps: { enabled: false },
    ...overrides,
  };
}

function closeTo(actual, expected, tolerance = 1e-9) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
}

test("browser-local DCF matches the disclosed period-end formula", () => {
  const input = defaultInput();
  const result = calculator.calculateDcfScreen(input);

  assert.equal(result.ok, true);
  const wacc = input.waccPct / 100;
  const growth = input.terminalGrowthPct / 100;
  const explicit = input.fcff.reduce(
    (total, cashFlow, index) => total + cashFlow / (1 + wacc) ** (index + 1),
    0,
  );
  const terminal = (input.fcff.at(-1) * (1 + growth)) / (wacc - growth);
  const expectedEv = explicit + terminal / (1 + wacc) ** input.fcff.length;
  closeTo(result.dcf.enterpriseValue, expectedEv);
  closeTo(result.bridge.equityValue, expectedEv + input.cash - input.debt - input.otherClaims);
  closeTo(result.bridge.valuePerShare, result.bridge.equityValue / input.dilutedShares);
  assert.equal(result.calculationIntegrity.status, "passed");
  assert.equal(result.decisionReadiness.status, "screen_grade");
  assert.equal(result.boundaries.persisted, false);
  assert.equal(result.boundaries.methodsAggregated, false);
});

test("WACC must be strictly above terminal growth", () => {
  const result = calculator.calculateDcfScreen(
    defaultInput({ waccPct: 3, terminalGrowthPct: 3 }),
  );

  assert.deepEqual(
    { ok: result.ok, code: result.code },
    { ok: false, code: "wacc_not_above_terminal_growth" },
  );
});

test("invalid sensitivity cells fail integrity and decision readiness", () => {
  const result = calculator.calculateDcfScreen(
    defaultInput({ waccPct: 1, terminalGrowthPct: 0.5 }),
  );

  assert.equal(result.ok, true);
  assert.equal(result.sensitivity.checks.cellsValid, false);
  assert.equal(result.calculationIntegrity.status, "failed");
  assert.equal(result.decisionReadiness.status, "not_ready");
  assert.ok(result.warnings.some((warning) => warning.includes("WACC ≤ g")));
});

test("illustrative multiple cross-check stays separate from DCF", () => {
  const result = calculator.calculateDcfScreen(
    defaultInput({
      comps: {
        enabled: true,
        metric: "EV/EBITDA",
        targetMetric: 13.2,
        lowMultiple: 7,
        baseMultiple: 8.5,
        highMultiple: 10,
      },
    }),
  );

  assert.equal(result.ok, true);
  closeTo(result.comparable.enterpriseValues.low, 92.4);
  closeTo(result.comparable.enterpriseValues.base, 112.2);
  closeTo(result.comparable.enterpriseValues.high, 132);
  assert.equal(result.boundaries.methodsAggregated, false);
  assert.notEqual(result.comparable.enterpriseValues.base, result.dcf.enterpriseValue);
});

test("illustrative multiples must be ordered low to high", () => {
  const result = calculator.calculateDcfScreen(
    defaultInput({
      comps: {
        enabled: true,
        metric: "EV/Revenue",
        targetMetric: 20,
        lowMultiple: 5,
        baseMultiple: 4,
        highMultiple: 6,
      },
    }),
  );

  assert.deepEqual(
    { ok: result.ok, code: result.code },
    { ok: false, code: "comps_range_order" },
  );
});

test("public screen rejects unsupported display units", () => {
  const result = calculator.calculateDcfScreen(defaultInput({ unit: "thousand" }));

  assert.deepEqual(
    { ok: result.ok, code: result.code },
    { ok: false, code: "invalid_unit" },
  );
});
