from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "public-preview"


def test_public_preview_valuation_is_local_only_and_explicitly_screen_grade() -> None:
    html = (PREVIEW / "index.html").read_text(encoding="utf-8")
    app = (PREVIEW / "app.js").read_text(encoding="utf-8")
    calculator = (PREVIEW / "valuation-calculator.js").read_text(encoding="utf-8")

    assert html.index('src="valuation-calculator.js?v=20260804-1"') < html.index(
        'src="app.js?v=20260804-1"'
    )
    assert 'id="valuation-calculator-form"' in html
    assert 'id="valuation-sensitivity-head"' in html
    assert "screen-grade 初算" in html
    assert "不发送、不保存" in html
    assert "不与 DCF 加权" in html
    assert "请勿输入敏感或保密信息" in html
    assert "Calculation integrity 与 decision readiness 分开呈现" in html
    assert "methodsAggregated: false" in calculator
    assert 'authority: "screen_grade_only"' in calculator
    assert 'id="valuation-wacc"' in html and 'step="any"' in html

    combined = "\n".join((html, app, calculator))
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
    ):
        assert forbidden not in combined


def test_public_preview_csp_disables_network_and_form_submission() -> None:
    config = json.loads((PREVIEW / "vercel.json").read_text(encoding="utf-8"))
    headers = {
        header["key"]: header["value"]
        for rule in config["headers"]
        for header in rule["headers"]
    }
    csp = headers["Content-Security-Policy"]
    assert "connect-src 'none'" in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors 'none'" in csp
