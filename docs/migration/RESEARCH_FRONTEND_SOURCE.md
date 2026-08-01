# Research 前端迁移来源

- 源仓库：`../ResearchMind`
- 固定提交：`40f7faa`
- 已导入历史路径：`.migration/researchmind/frontend/`
- 目标集成路径：`apps/web/src/modules/research/`
- 迁移所属专项：统一前端信息架构计划

源前端有意不在 EvidSight 根目录中保持可运行状态。其页面、Store、API 客户端行为、SSE 解析器、测试和原型必须先通过前端专项设计建立映射，再进行选择性迁移。
