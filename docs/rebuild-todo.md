# 重构待做项（2026-04-14 更新）

## 已完成

- [x] 状态驱动执行内核（sense/decide/act/verify）
- [x] 上下文管理与上下文切换（context_id）
- [x] Controller 路由模型（跨软件控制单元）
- [x] 分层状态机数据结构（global/context/controller）
- [x] 感知不确定性模型（PerceptionResult）
- [x] 统一恢复矩阵（RecoveryStrategy）
- [x] 资源仲裁（ResourceArbiter）
- [x] 日志序列号与时间线回放工具（run replay）
- [x] AI 恢复规划器接口预留（AiRecoveryPlannerPort）
- [x] 原神+bettergi profile 接入 context/controller 标注

## 待完成

- [ ] 真实视觉能力接入（OCR/模板匹配）
- [ ] WindowPort（真实窗口聚焦校验 + 切换失败恢复）
- [ ] AI 安全闸（白名单动作 + 限流 + 风险区域封禁）
- [ ] 关键业务状态图细化（按 `rebuild-mapping.md`）
- [ ] Windows 实机端到端回归

## 测试状态

- [x] 单元测试通过：24/24
