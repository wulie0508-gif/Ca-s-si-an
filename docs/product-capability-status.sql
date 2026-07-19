WITH capability_status(order_id, module, state, delivers, boundary) AS (
    SELECT 1, '企业入驻与本地工作台', '当前可运行', '案例、授权、访谈、材料、主张、证据、闸门与本地工作包', '不是完整企业门户或在线协作平台'
    UNION ALL SELECT 2, '证据治理与内容权限', '当前可运行', 'E0–E4、主张状态、可见级别、发布授权与人工审核边界', '管理层原话和 Agent 结果不会自动成为事实'
    UNION ALL SELECT 3, '盈利/单位经济性', '端到端已验证', '可引用事实、确定性计算、规则、双语五格证据卡', '不是投资或信用评级'
    UNION ALL SELECT 4, '现金流/资金缺口', '端到端已验证', '现金事实、公式、资金缺口相关证据卡与人工复核项', '不替代财务预测或融资承诺'
    UNION ALL SELECT 5, '其他四项财务维度', '仅有输入蓝图', '字段与证据需求的结构化方向', '不能称为可执行、已验证分析'
    UNION ALL SELECT 6, 'ESG 全面审查', '证据框架', '材料、主张、缺口与后续规则库承载结构', '不是 ESG 保证、认证或完整自动评分'
    UNION ALL SELECT 7, 'DOE ARL 相关分析', '17 维检索脚手架', '商业化风险证据的检索组织方式', '不复制官方问卷、不计算 ARL 1–9 分数、不代表 DOE'
    UNION ALL SELECT 8, '同业同阶段比较', '已有安全合约', '同子行业、阶段、商业模式、国家与期间的比较结构', '样本少于 5 不输出百分位，不跨阶段做总排名'
    UNION ALL SELECT 9, '企业补件中心', '本轮重点设计', '把缺口转成完整提交、退回、接受、回填与重算闭环', '尚未完成 UI、持久化和 API 工程'
    UNION ALL SELECT 10, '统一加权总分', '未交付', '当前明确保留各维度证据与阶段差异', '不输出综合投资、信用或风险评级'
)
SELECT order_id AS "order", module, state, delivers, boundary
FROM capability_status
ORDER BY order_id;
