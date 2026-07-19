WITH information_lifecycle(order_id, state, meaning, upgrade, prohibited) AS (
    SELECT 1, '原始记录 Raw record', '录音、转写、文件、网页快照或 Agent 原始产物', '记录来源、时间、哈希、实体与版本', '不能因为来源看起来权威就直接成为结论'
    UNION ALL SELECT 2, '管理层陈述 Statement', '证明某人在某个上下文中作出过该表达', '切分为可检验的原子主张并保留说话人和上下文', '访谈原话不等于已证实事实'
    UNION ALL SELECT 3, '主张/假设 Claim', '可以被支持、反驳或判定不适用的最小判断单元', '定义范围、期间、单位、重要性和最低证据等级', '不能用模糊复合句隐藏多个未验证问题'
    UNION ALL SELECT 4, '候选证据 Evidence', '与主张关联的内部、交易、官方、外部或独立材料', '通过实体、期间、来源、内容、冲突与证据等级审核', 'Agent 候选材料不能自动接受'
    UNION ALL SELECT 5, '事实状态 Fact status', 'verified、partially_verified、unverified、conflicted、refuted 或 not_applicable', '人工审核确认，关键主张达到规定证据等级', '缺失、冲突和不适用不能被静默吞掉'
    UNION ALL SELECT 6, '分析发现 Finding', '确定性计算、规则应用或带证据的专业判断', '记录输入、公式/规则版本、适用范围、限制和复核人', '不能把不同成熟度维度强行汇总成总分'
    UNION ALL SELECT 7, '批准发布 Public approved', '可进入外部报告、公司 IP 或传播内容的事实表述', '事实已验证且内容、身份/品牌、翻译等权限均满足', '内部可见不等于可以公开'
)
SELECT order_id AS "order", state, meaning, upgrade, prohibited
FROM information_lifecycle
ORDER BY order_id;
