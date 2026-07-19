-- Engine: SQLite
-- Purpose: executable source query for the portable report's headline cards
-- and the real five-company count chart.
--
-- These values are a structured transcription of
-- docs/project-status-validation-receipt-2026-07-18.md. The receipt and its
-- repository evidence anchors remain the upstream audit evidence. This query
-- exists so the portable report's data-backed widgets have an exact,
-- reproducible SQL source rather than a prose or shell command disguised as
-- SQL.

SELECT 'metric_tests' AS dataset, NULL AS status, 145 AS value
UNION ALL
SELECT 'metric_schemas', NULL, 7
UNION ALL
SELECT 'metric_finance_references', NULL, 2
UNION ALL
SELECT 'metric_registry', NULL, 10
UNION ALL
SELECT 'metric_real_five', NULL, 0
UNION ALL
SELECT 'five_company_count', '已执行', 0
UNION ALL
SELECT 'five_company_count', '尚待执行', 5;

SELECT 1 AS "order", '完整 pytest' AS "check",
       '145 passed' AS result,
       '当前工作树完整测试集合' AS evidence,
       '代码合同与回归测试全绿；不等于五企交付' AS interpretation
UNION ALL
SELECT 2, 'Ruff', 'All checks passed', '仓库 Python 静态检查',
       '未观察到 Ruff 规则违例'
UNION ALL
SELECT 3, 'JSON Schema', '7/7 valid', 'Draft 2020-12 Schema 校验',
       'Schema 语法与元 Schema 有效'
UNION ALL
SELECT 4, 'Sungrow 顺序发布门禁', '通过',
       'extraction 29/29；cards 27/27；citations 112；model calls 0',
       '既有两项财务维度的参考链未观察到回归'
UNION ALL
SELECT 5, 'Enphase 顺序发布门禁', '通过',
       'extraction 28/28；cards 27/27；citations 113；model calls 0',
       '第二个既有参考链未观察到回归'
UNION ALL
SELECT 6, '十家公司财务注册表', '10/10 pass',
       '所有运行 model calls 0',
       '历史泛化回归健康；不能替代本轮五家'
UNION ALL
SELECT 7, '本地索引', '已重新生成', '当前报告入口与案例索引刷新',
       '本地工作台可浏览最新静态输出'
UNION ALL
SELECT 8, '浏览器桌面与 375px', '通过',
       '无页面级横向溢出；回归与保证字段可见；console 0 errors/warnings',
       '本轮已观察的报告布局可用'
UNION ALL
SELECT 9, '正式五企产物盘点', '0 个',
       'qa_delivery JSON 0；候选 qa registry 0',
       '真实五企交付尚未执行，不能以绿灯推断完成';
