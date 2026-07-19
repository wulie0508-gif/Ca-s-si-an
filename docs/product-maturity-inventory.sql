WITH maturity_inventory(label, count, domain, status, definition) AS (
    SELECT
        '财务｜端到端已验证',
        2,
        'Financial',
        'validated',
        '能够完成抽取、计算、规则、证据卡与验证门禁'
    UNION ALL
    SELECT
        '财务｜仅输入蓝图',
        4,
        'Financial',
        'authored',
        '已有字段和证据需求设计，但尚不可执行或未验证'
    UNION ALL
    SELECT
        'ARL｜检索脚手架',
        17,
        'DOE ARL',
        'retrieval scaffold',
        '只组织候选证据检索，不产生自动判断或分数'
    UNION ALL
    SELECT
        'ARL｜端到端已验证',
        0,
        'DOE ARL',
        'not validated',
        '当前没有经过验证的自动 ARL 判断维度'
)
SELECT label, count, domain, status, definition
FROM maturity_inventory;
