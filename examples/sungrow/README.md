# Sungrow 2025 test case

This case uses Sungrow Power Supply Co., Ltd. (SZSE:300274), a listed manufacturer of PV inverters and energy storage systems.

## Public source

- [CNINFO disclosure detail](https://www.cninfo.com.cn/new/disclosure/detail?orgId=9900021300&announcementId=1225358186&announcementTime=2026-06-08%2018:54)
- [English annual report PDF](https://static.cninfo.com.cn/finalpage/2026-06-08/1225358186.PDF)

CNINFO is the statutory disclosure platform designated by the Shenzhen Stock Exchange. The PDF is downloaded into `.cache/` and is not redistributed by this repository.

## Run

```bash
python scripts/download_demo_sources.py sungrow
python scripts/download_demo_sources.py enphase
cleantech-finance audit examples/sungrow/manifest.auto.json \
  --only profitability-unit-economics cash-runway \
  --out outputs/sungrow
python scripts/evaluate_audit.py outputs/sungrow/audit.json evals/sungrow-2025.json
python scripts/evaluate_cards.py \
  outputs/sungrow/audit.json evals/sungrow-cards-v0.2.json
```

`manifest.auto.json` contains no subject-company financial values. Six audited inputs are extracted from consolidated statement windows. The Enphase filing is assigned `role: benchmark`: it can support the cited relative-comparison stage but is excluded from Sungrow's subject-evidence retrieval and fact extraction. `manifest.json` contains a manually cited version for comparison and for testing the structured-input path.

## Verified result

- Automatic fact extraction: six of six required facts for both FY2025 and FY2024
- Exact statement locations: pages 135, 139, and 140
- Revenue growth: 14.5%
- Gross margin: 31.8%
- Free cash flow: CNY 13.910bn
- Capex to revenue: 3.4%
- Cash runway: intentionally not calculated because observed free cash flow was positive
- Five-cell profitability card: green evidence signal, with own-history trend primary and Enphase explicitly limited as an adjacent reference
- Five-cell cash card: green evidence signal, because the profitable-company branch shows improving historical operating-cash-flow coverage of capex
- Card contract regression: 27/27

The research cards remain a starting point for human review. In particular, positive historical free cash flow does not resolve forward capex, working-capital, project-finance, warranty, or downside risk. The green labels are evidence signals, not investment or credit ratings.
