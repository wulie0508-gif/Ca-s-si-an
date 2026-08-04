"use strict";

(function registerValuationCalculator(root, factory) {
  const calculator = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = calculator;
  }
  if (root) {
    root.CleanTechValuationCalculator = calculator;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createCalculator() {
  const WACC_DELTAS = [-0.02, -0.01, 0, 0.01, 0.02];
  const GROWTH_DELTAS = [-0.01, -0.005, 0, 0.005, 0.01];

  class ValuationInputError extends Error {
    constructor(code, message) {
      super(message);
      this.name = "ValuationInputError";
      this.code = code;
    }
  }

  function finiteNumber(value, label, { minimum = null, maximum = null } = {}) {
    const result = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(result)) {
      throw new ValuationInputError("invalid_number", `${label} 必须是有限数字。`);
    }
    if (minimum !== null && result < minimum) {
      throw new ValuationInputError("below_minimum", `${label} 不能低于 ${minimum}。`);
    }
    if (maximum !== null && result > maximum) {
      throw new ValuationInputError("above_maximum", `${label} 不能高于 ${maximum}。`);
    }
    return result;
  }

  function optionalNonNegative(value, label) {
    if (value === "" || value === null || value === undefined) {
      return 0;
    }
    return finiteNumber(value, label, { minimum: 0 });
  }

  function normalizeInput(input) {
    const fcff = Array.isArray(input.fcff)
      ? input.fcff.map((value, index) => finiteNumber(value, `第 ${index + 1} 年 FCFF`))
      : [];
    if (fcff.length < 1 || fcff.length > 10) {
      throw new ValuationInputError("forecast_length", "DCF 需要 1 至 10 个年度 FCFF 预测。 ");
    }
    if (fcff.at(-1) <= 0) {
      throw new ValuationInputError(
        "terminal_fcff_not_positive",
        "最后一年 FCFF 必须大于 0，才能使用永续增长终值。",
      );
    }

    const wacc = finiteNumber(input.waccPct, "WACC", { minimum: 0.0001, maximum: 99 }) / 100;
    const terminalGrowth = finiteNumber(input.terminalGrowthPct, "终值增长率", {
      minimum: -99,
      maximum: 99,
    }) / 100;
    if (wacc <= terminalGrowth) {
      throw new ValuationInputError(
        "wacc_not_above_terminal_growth",
        "WACC 必须严格高于终值增长率。",
      );
    }

    const discountConvention = input.discountConvention || "period_end";
    if (!["period_end", "mid_year"].includes(discountConvention)) {
      throw new ValuationInputError("invalid_discount_convention", "请选择有效的折现时点。 ");
    }

    const currency = String(input.currency || "CNY").trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(currency)) {
      throw new ValuationInputError("invalid_currency", "币种必须使用三位字母代码。 ");
    }

    const unit = String(input.unit || "million").trim() || "million";
    if (!["million", "billion"].includes(unit)) {
      throw new ValuationInputError("invalid_unit", "公开初算仅支持百万或十亿单位。 ");
    }

    return {
      fcff,
      wacc,
      terminalGrowth,
      discountConvention,
      currency,
      unit,
      cash: optionalNonNegative(input.cash, "现金及类现金"),
      debt: optionalNonNegative(input.debt, "债务类项目"),
      otherClaims: optionalNonNegative(input.otherClaims, "其他债权与少数股东权益"),
      dilutedShares:
        input.dilutedShares === "" || input.dilutedShares === null || input.dilutedShares === undefined
          ? null
          : finiteNumber(input.dilutedShares, "完全摊薄股数", { minimum: 0.000001 }),
      comps: input.comps || null,
    };
  }

  function discountExponent(periodIndex, convention) {
    return convention === "mid_year" ? periodIndex - 0.5 : periodIndex;
  }

  function dcfEnterpriseValue(fcff, wacc, terminalGrowth, convention) {
    if (wacc <= terminalGrowth) {
      throw new ValuationInputError(
        "wacc_not_above_terminal_growth",
        "WACC 必须严格高于终值增长率。",
      );
    }
    const projections = fcff.map((cashFlow, index) => {
      const period = index + 1;
      const exponent = discountExponent(period, convention);
      const presentValue = cashFlow / Math.pow(1 + wacc, exponent);
      return { period, fcff: cashFlow, discountExponent: exponent, presentValue };
    });
    const presentValueExplicit = projections.reduce((total, item) => total + item.presentValue, 0);
    const terminalValue = (fcff.at(-1) * (1 + terminalGrowth)) / (wacc - terminalGrowth);
    const terminalExponent = discountExponent(fcff.length, convention);
    const presentValueTerminal = terminalValue / Math.pow(1 + wacc, terminalExponent);
    const enterpriseValue = presentValueExplicit + presentValueTerminal;
    if (![presentValueExplicit, terminalValue, presentValueTerminal, enterpriseValue].every(Number.isFinite)) {
      throw new ValuationInputError("non_finite_output", "输入导致无法计算的非有限结果。 ");
    }
    return {
      projections,
      presentValueExplicit,
      terminalValue,
      presentValueTerminal,
      enterpriseValue,
      terminalValueShareOfEv: enterpriseValue === 0 ? null : presentValueTerminal / enterpriseValue,
    };
  }

  function equityBridge(enterpriseValue, input) {
    const equityValue = enterpriseValue + input.cash - input.debt - input.otherClaims;
    return {
      enterpriseValue,
      cash: input.cash,
      debt: input.debt,
      otherClaims: input.otherClaims,
      equityValue,
      dilutedShares: input.dilutedShares,
      valuePerShare: input.dilutedShares === null ? null : equityValue / input.dilutedShares,
      formula: "Equity value = Enterprise value + Cash − Debt − Other claims",
    };
  }

  function sensitivityTable(input) {
    const rows = Array.from(
      new Set(WACC_DELTAS.map((delta) => Math.max(0.000001, input.wacc + delta))),
    ).sort((left, right) => left - right);
    const columns = Array.from(
      new Set(GROWTH_DELTAS.map((delta) => input.terminalGrowth + delta)),
    ).sort((left, right) => left - right);
    const cells = rows.map((wacc) =>
      columns.map((growth) => {
        if (wacc <= growth) {
          return { value: null, status: "invalid" };
        }
        const result = dcfEnterpriseValue(input.fcff, wacc, growth, input.discountConvention);
        return { value: result.enterpriseValue, status: "value" };
      }),
    );

    let waccDirectionPassed = true;
    for (let columnIndex = 0; columnIndex < columns.length; columnIndex += 1) {
      const values = cells.map((row) => row[columnIndex].value).filter((value) => value !== null);
      for (let index = 1; index < values.length; index += 1) {
        if (values[index] > values[index - 1] + Number.EPSILON) {
          waccDirectionPassed = false;
        }
      }
    }

    let growthDirectionPassed = true;
    cells.forEach((row) => {
      const values = row.map((cell) => cell.value).filter((value) => value !== null);
      for (let index = 1; index < values.length; index += 1) {
        if (values[index] + Number.EPSILON < values[index - 1]) {
          growthDirectionPassed = false;
        }
      }
    });

    const cellsValid = cells.every((row) => row.every((cell) => cell.status === "value"));
    return {
      rows,
      columns,
      cells,
      checks: {
        cellsValid,
        higherWaccLowersValue: waccDirectionPassed,
        higherGrowthRaisesValue: growthDirectionPassed,
      },
    };
  }

  function comparableCrossCheck(comps, input) {
    if (!comps || comps.enabled === false) {
      return null;
    }
    const targetMetric = finiteNumber(comps.targetMetric, "目标 LTM 指标", { minimum: 0.000001 });
    const lowMultiple = finiteNumber(comps.lowMultiple, "低位倍数", { minimum: 0.000001 });
    const baseMultiple = finiteNumber(comps.baseMultiple, "中位倍数", { minimum: 0.000001 });
    const highMultiple = finiteNumber(comps.highMultiple, "高位倍数", { minimum: 0.000001 });
    if (!(lowMultiple <= baseMultiple && baseMultiple <= highMultiple)) {
      throw new ValuationInputError(
        "comps_range_order",
        "可比倍数必须满足低位 ≤ 中位 ≤ 高位。",
      );
    }
    const metric = String(comps.metric || "EV/EBITDA");
    if (!["EV/EBITDA", "EV/Revenue"].includes(metric)) {
      throw new ValuationInputError("unsupported_comps_metric", "公开初算仅支持 EV/EBITDA 或 EV/Revenue。 ");
    }

    const lowEnterpriseValue = targetMetric * lowMultiple;
    const baseEnterpriseValue = targetMetric * baseMultiple;
    const highEnterpriseValue = targetMetric * highMultiple;
    return {
      metric,
      targetMetric,
      multiples: { low: lowMultiple, base: baseMultiple, high: highMultiple },
      enterpriseValues: {
        low: lowEnterpriseValue,
        base: baseEnterpriseValue,
        high: highEnterpriseValue,
      },
      equityValues: {
        low: equityBridge(lowEnterpriseValue, input),
        base: equityBridge(baseEnterpriseValue, input),
        high: equityBridge(highEnterpriseValue, input),
      },
      formula: `${metric} × human-entered target metric`,
      rangeBasis: "user_entered_low_base_high",
    };
  }

  function calculateDcfScreen(rawInput) {
    try {
      const input = normalizeInput(rawInput || {});
      const dcf = dcfEnterpriseValue(
        input.fcff,
        input.wacc,
        input.terminalGrowth,
        input.discountConvention,
      );
      const bridge = equityBridge(dcf.enterpriseValue, input);
      const warnings = [
        "预测、WACC 和终值增长率均为手工输入，尚未绑定来源。",
        "浏览器结果不会写入版本、哈希或审计链。",
        "公开初算使用简化桥接，未覆盖非经营资产、租赁、养老金等需专业重分类项目。",
      ];
      if (input.comps && input.comps.enabled !== false) {
        warnings.push("可比倍数及目标指标为手工输入，尚未绑定来源。 ");
      }
      if (dcf.terminalValueShareOfEv !== null && dcf.terminalValueShareOfEv > 0.75) {
        warnings.push("终值现值超过企业价值的 75%，结果对长期假设高度敏感。 ");
      }
      if (input.fcff.some((value) => value <= 0)) {
        warnings.push("显性预测中包含非正 FCFF，请复核经营与再投资假设。 ");
      }
      if (bridge.equityValue <= 0) {
        warnings.push("EV→股权桥接后股权价值不为正，请复核债务类项目和企业价值。 ");
      }
      if (input.dilutedShares === null) {
        warnings.push("未提供完全摊薄股数，因此不输出每股价值。 ");
      }

      const sensitivity = sensitivityTable(input);
      if (!sensitivity.checks.cellsValid) {
        warnings.push("敏感性区间含有 WACC ≤ g 的无效单元格，计算完整性未通过。 ");
      }
      const comparable = comparableCrossCheck(input.comps, input);
      const directionChecksPassed =
        sensitivity.checks.higherWaccLowersValue && sensitivity.checks.higherGrowthRaisesValue;
      const integrityPassed = directionChecksPassed && sensitivity.checks.cellsValid;

      return {
        ok: true,
        model: "browser-local-dcf-screen-1.0",
        authority: "screen_grade_only",
        input: {
          ...input,
          waccPct: input.wacc * 100,
          terminalGrowthPct: input.terminalGrowth * 100,
        },
        dcf,
        bridge,
        comparable,
        sensitivity,
        calculationIntegrity: {
          status: integrityPassed ? "passed" : "failed",
          checks: {
            waccAboveTerminalGrowth: true,
            finiteOutputs: true,
            sensitivityCellsValid: sensitivity.checks.cellsValid,
            sensitivityDirectionality: directionChecksPassed,
          },
        },
        decisionReadiness: {
          status: integrityPassed ? "screen_grade" : "not_ready",
          humanReviewRequired: true,
          blockingReasons: [
            "关键假设未绑定来源或负责人确认",
            "结果未进入版本、哈希和人工复核工作流",
            ...(!integrityPassed ? ["敏感性控制区间存在无效单元格或方向检查失败"] : []),
          ],
        },
        warnings,
        boundaries: {
          persisted: false,
          uploaded: false,
          investmentRatingProduced: false,
          methodsAggregated: false,
          formalValuationOpinionProduced: false,
        },
      };
    } catch (error) {
      if (error instanceof ValuationInputError) {
        return { ok: false, code: error.code, message: error.message };
      }
      throw error;
    }
  }

  return {
    ValuationInputError,
    calculateDcfScreen,
  };
});
