# EvidSight 跟踪版交互原型

本目录是 `apps/web` 的已跟踪视觉实现参考，用于还原页面信息层级、壳层、动作位置、排版节奏、品牌资产和交互表面。它不是第二套生产前端，不进入 Vite 构建、部署或运行时依赖。

## 权威边界

发生冲突时按以下顺序处理：

1. 业务行为、权限、路由与数据：`docs/specs/`、`apps/web/docs/FRONTEND.md` 和已接受 ADR；
2. 视觉语义与 Design Token：`apps/web/docs/UIDESIGN.md`；
3. 页面结构、动作位置和品牌资产：本目录；
4. 像素与主题参考：`resource/prototype/light/`、`resource/prototype/dark/`。

原型不得覆盖上级规范。发现冲突时暂停实现，按文档治理流程裁决。

## 已知覆盖规则

- Chat v1.0 只允许单个知识库。原型中遗留的多选 Checkbox、已选两个知识库及相关示例文案不得进入生产实现；选择器形态可以复用，但行为服从 ADR-001 和 FRONTEND。
- Billing、角色配置和系统设置是 P1 视觉演进基线，不得渲染为 v1.0 已上线能力。
- 原型内 `--midnight`、`--line` 等变量仅属于原型自身。生产代码只能使用 UIDESIGN 登记的 `--es-*` Token，禁止复制旧变量名或颜色字面量。
- 原型的 Google Fonts 引用不进入生产实现。生产字体与图标必须按 UIDESIGN 的资产登记本地化。
- 原型 Hash 路由、Mock 数据和 `app.js` 只用于展示状态，不定义 React 路由、API、权限或状态机。

## 使用方式

- 页面与截图映射见 `prototype-manifest.json`。
- `index-light.html` 展示默认浅色工作区；入口页仍固定使用深色品牌叙事。
- `index.html` 展示深色工作区选项。
- 修改本目录必须同步检查 manifest、两套截图和 UIDESIGN；不得只改原型而让权威规范失配。
