WITH five_gates(order_id, gate, question, failure) AS (
    SELECT 1, '授权闸门', '是否获得内部分析、录音/转写、公开内容、身份/品牌、翻译或 AI 媒体的对应授权？', '停止相关用途，但不影响其他已获授权的本地工作'
    UNION ALL SELECT 2, '主体与范围闸门', '法律主体、国家、行业、商业模式、阶段、产品/技术和分析范围是否明确？', '生成主体/范围补件，不进入可比较分析'
    UNION ALL SELECT 3, '最低证据闸门', '阶段所需材料是否齐备，关键主张是否达到最低证据要求？', '转换为企业补件任务或人工取证任务'
    UNION ALL SELECT 4, '分析资格闸门', '前置闸门是否通过，目标专业模块是否已验证且适用于当前企业？', '保留为证据框架或人工研究，不输出自动结论'
    UNION ALL SELECT 5, '发布闸门', '内容是否已验证、已获发布和品牌授权，并完成最终人工审核？', '保持 internal、restricted 或 public_candidate 状态'
)
SELECT order_id AS "order", gate, question, failure
FROM five_gates
ORDER BY order_id;
