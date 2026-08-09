# EvidSight Web UI Design System

> 设计方向：默认浅色办公主题，深色为主题选项（入口页保留品牌深色叙事）  
> 状态：v1.1 浅色默认基线  
> 最后更新：2026-08-06  
> 页面与交互规范：[FRONTEND.md](FRONTEND.md)  
> 原型截图目录：[resource/prototype](../../../resource/prototype)

## 1. 设计目标

EvidSight 的界面是一台“专业研究仪器”，不是传统后台模板、聊天机器人皮肤或自然风知识产品。产品默认使用浅色办公主题，并保留深色主题作为可选外观；入口叙事页保留品牌深色氛围。视觉需要同时表达：

- 简洁：清楚的区域边界、少量层级和充分留白；
- 高级：精确排版、克制材质与一致细节；
- 可读：工作型产品以信息对比度优先，正文与辅助文字在任一主题下都满足 WCAG AA；
- 可信：引用、状态、限制和权限始终可见，不用装饰掩盖事实。

核心原则是“证据发光，界面退后”。高亮只用于当前动作、当前证据和系统状态，不能大面积铺满页面。

## 2. 视觉禁区

禁止：

- 紫色、洋红或高饱和赛博朋克渐变；
- 纯黑大平面作为唯一背景，或以深色作为唯一默认主题掩饰可读性问题；
- 大量玻璃拟态、发光描边和阴影卡片；
- 绿色作为品牌主色；
- 无业务意义的 KPI Bento；
- 装饰性机器人头像、Emoji 或字符拼成的导航图标；
- 通用放大镜、脑、火花、数据库方块作为品牌主图标；
- 过多胶囊按钮或所有元素都圆角化；
- 为追求“高级”而降低正文、列表和操作按钮的可读性。

## 3. 品牌系统

### 3.1 名称与语气

中文名“据见”，英文名 `EvidSight`。界面优先使用 `EvidSight` 品牌字标，中文用于产品叙事。语气冷静、直接、有判断边界：

- 推荐：“没有凭据，不立结论”；
- 推荐：“看见线索之间真正重要的联系”；
- 避免：“AI 赋能未来”“一键洞察一切”等无法验证的夸张表达。

### 3.2 品牌主图标

品牌 Mark 由断开的非对称轨道、三枚证据节点和一个汇聚视点构成，暗示“证据进入视野并形成关系”。要求：

- 24px 仍能辨识；
- 单色可用；
- 外圈保留一个开口，避免监控眼意象；
- 仅一个节点允许使用 spectral cyan；
- 不放入通用彩色圆角方块。

### 3.3 入口叙事

入口页采用全屏叙事流。Hero 使用巨型但受控的中文标题、轨道线和单一亮点。背景的艺术感来自线、噪声和低亮度径向光，不使用照片、自然纹理或动画星空。入口页固定保留深色品牌叙事，不随用户主题选择切换；登录抽屉与登录后的工作区默认使用浅色主题。

## 4. Design Token

Token 是跨主题共享的语义变量。深浅主题只改变 Token 的值，不改变 Token 名称与业务组件的使用方式；业务组件禁止硬编码颜色，只能消费 `--es-*` Token。

### 4.0 Token 注册与闭包门禁

本节是生产 Web Design Token 的唯一注册表。只有本节登记的 `--es-*` 名称可以进入 `apps/web/src/`；不得自行发明 `--es-line`、`--es-radius-sm` 等别名，也不得把交互原型中的 `--midnight`、`--line` 等旧变量复制到生产代码。

Token 约束：

- `apps/web/src/styles/tokens.css` 是本节的实现投影，不是反向定义规范的来源；名称和值必须与本节一致；
- `apps/web/src/` 引用但未在 `tokens.css` 声明的 `--es-*` 必须使静态门禁失败；
- 除 `tokens.css`、已登记品牌 SVG 和第三方样式外，生产源码不得出现颜色字面量；遮罩与阴影也必须使用 Token；
- 深浅主题复用同一组语义名称。仅颜色与表面效果允许按主题换值，尺寸和字体 Token 从根级继承；
- Tailwind Theme 只能映射已登记 Token；不得在 Tailwind 配置中建立第二套颜色、圆角或字体事实；
- spacing 允许直接使用 `4/8/12/16/24/32/48/64px`；其他间距必须先经本节评审，不为每个间距重复建立变量；
- 组件内部只表达运行数据的局部 CSS 变量（例如进度百分比）可以不使用 `--es-*`，但不得承载颜色、字体、圆角、阴影或布局基线。

除 §4.2 的主题色 Token 外，正式登记如下：

| 类别 | Token | 固定值 / 语义 |
|---|---|---|
| 圆角 | `--es-radius-control` | `8px`，输入、按钮和紧凑控件 |
| 圆角 | `--es-radius-panel` | `10px`，普通面板与 Popover |
| 圆角 | `--es-radius-major` | `12px`，主要表面与大型 Overlay |
| 字体 | `--es-font-sans` | `Inter` + 中文系统黑体 + `system-ui` |
| 字体 | `--es-font-display` | `Space Grotesk` + 中文系统黑体 + `system-ui` |
| 字体 | `--es-font-mono` | `JetBrains Mono` + `ui-monospace` |
| 遮罩 | `--es-overlay` | `rgb(0 0 0 / 40%)`，Drawer 与 Dialog 共用 |
| 主题选择 | `--es-swatch-light` | 浅色选项色板（固定表示，与当前主题无关） |
| 主题选择 | `--es-swatch-dark` | 深色选项色板（固定表示，与当前主题无关） |
| 阴影 | `--es-shadow-drawer` | `-24px 0 80px rgb(0 0 0 / 16%)` |
| 阴影 | `--es-shadow-popover` | `0 16px 40px rgb(0 0 0 / 14%)` |
| 阴影 | `--es-shadow-dialog` | `0 24px 80px rgb(0 0 0 / 20%)` |
| 阴影 | `--es-shadow-floating` | `0 12px 32px rgb(0 0 0 / 14%)` |
| 入口叙事 | `--es-landing-gradient` | 入口页多层深色品牌渐变背景（不随主题切换） |
| 入口叙事 | `--es-landing-grid` | Hero 网格线背景 |
| 入口叙事 | `--es-landing-grid-mask` | Hero 网格径向遮罩 |
| 入口叙事 | `--es-landing-trace-secondary` | Hero 次级轨道线 |
| 入口叙事 | `--es-landing-contour` | Hero 轮廓线 |
| 入口叙事 | `--es-landing-coordinate` | Hero 坐标标注 |
| 入口叙事 | `--es-landing-proof` | Hero 底注与页脚文字 |
| 入口叙事 | `--es-landing-cta-gradient` | 发光主按钮渐变 |

入口叙事页专属 Token 只在 `.landing` 作用域内取深色品牌值；业务组件不得在入口之外消费，其值统一登记在 `tokens.css` 的深色作用域块。生产首次通过视觉 GREEN 前，`Inter`、`Space Grotesk`、`JetBrains Mono` 和选定图标字体的 WOFF2 必须进入 `apps/web/src/assets/fonts/` 并通过 `@font-face` 本地加载；只在 Token 中写字体名称不算完成。第三方 CDN 不作为发布或视觉验收依赖。

### 4.1 主题与默认

- 默认主题为浅色（`data-theme="light"`）：登录抽屉与登录后的工作区默认浅色。
- 深色主题（`data-theme="dark"`）是用户可选外观：通过账号菜单「主题选择」的两步骤确认流程切换（视觉规格见 §7.21 主题选择卡片），确认后生效并持久化到 `localStorage`（键 `evidsight-theme`）。
- 入口叙事页固定深色品牌氛围，不随主题切换。
- 入口深色作用域：`tokens.css` 的深色块把 `.landing`（含 `.landing[data-theme='light']`）一并纳入选择器，因此入口子树无论工作区主题如何恒取深色 Token 值；登录抽屉与入口页是同层兄弟，不受该作用域影响，默认浅色。
- 切换机制：`<html data-theme="light|dark">` + CSS Variables；未显式选择时可参考 `prefers-color-scheme` 降级，但用户显式选择始终优先。
- 深浅两套 Token 值由 4.2 定义，任一主题下正文与辅助文字均须满足 WCAG AA。

### 4.2 色彩 Token

浅色主题（默认，`data-theme="light"`）：

```css
:root, :root[data-theme='light'] {
  --es-canvas: #f3f4f6;
  --es-surface: #ffffff;
  --es-surface-muted: #f8fafb;

  --es-ink-primary: #161d24;
  --es-ink-secondary: #46525f;
  --es-ink-muted: #6b7682;
  --es-ink-disabled: #9aa3ad;

  --es-moonstone: #3d6d94;
  --es-moonstone-hover: #2b5c85;
  --es-moonstone-soft: rgb(61 109 148 / 10%);
  --es-spectral-cyan: #0b8f8b;

  --es-success: #0a9d6b;
  --es-warning: #b45309;
  --es-danger: #d64554;
  --es-knowledge: #4168c9;

  --es-border-subtle: rgb(16 21 28 / 8%);
  --es-border-default: rgb(16 21 28 / 12%);
  --es-border-strong: rgb(16 21 28 / 22%);
  --es-focus: #3d6d94;
}
```

深色主题（可选，`data-theme="dark"`）：

```css
:root[data-theme='dark'] {
  --es-canvas: #07090f;
  --es-surface: #0d111a;
  --es-surface-muted: #151a27;

  --es-ink-primary: #f4f5f8;
  --es-ink-secondary: #b6c2ca;
  --es-ink-muted: #8d9ba6;
  --es-ink-disabled: #505563;

  --es-moonstone: #a9c7d8;
  --es-moonstone-hover: #c2d9e5;
  --es-moonstone-soft: rgb(169 199 216 / 12%);
  --es-spectral-cyan: #70d3d0;

  --es-success: #54c99a;
  --es-warning: #d8a84e;
  --es-danger: #e7677a;
  --es-knowledge: #6e8fe8;

  --es-border-subtle: rgb(244 245 248 / 8%);
  --es-border-default: rgb(244 245 248 / 12%);
  --es-border-strong: rgb(244 245 248 / 22%);
  --es-focus: #c2d9e5;
}
```

状态色必须配合图标、文案或形状。`spectral-cyan` 表示 Evidence、实时连接或精确选中；`knowledge` 只表示内部知识通道；`success` 不能替代品牌色。

### 4.3 背景材质

- 浅色主题（默认）：`--es-canvas` 平铺浅灰，内容区以 `--es-surface` 白色容器承载，容器间用 1px Hairline 分隔；不使用噪声或径向光，保证办公环境干净、分区清楚。
- 深色主题（可选）：保留三层背景（基础渐变、右上 moonstone 径向光与左下青色雾、2%–3% 单色噪声），并遵守「界面退后」原则，不以装饰降低文字对比。

噪声作为独立伪元素，`pointer-events: none`，不得降低文字对比。大面积内容区不能因多层半透明产生色带或滚动性能问题。

### 4.4 字体

| 用途 | 字体 | 尺寸/行高 |
|---|---|---|
| 营销 Hero | Space Grotesk / 中文系统黑体 | `clamp(48px, 6vw, 88px)` / 0.96–1.05 |
| 页面标题 | Space Grotesk / 中文系统黑体 | 32–44px / 1.1 |
| 报告标题 | Space Grotesk / 中文系统黑体 | 38–48px / 1.08 |
| 区块标题 | Space Grotesk / Inter | 20–28px / 1.25 |
| 列表主标题 | Inter / 中文系统黑体 | 15–16px / 1.45 |
| 正文 | Inter / 中文系统黑体 | 14–16px / 1.65 |
| 报告正文 | Inter / 中文系统字体 | 16px / 1.85 |
| 导航 | Inter | 14px / 1.4 |
| 元数据 | JetBrains Mono | 10–12px / 1.4 |

中文字体回退建议：`"PingFang SC", "Microsoft YaHei", system-ui, sans-serif`。等宽字体只用于短标签、Trace ID、阶段和时间，不用于中文段落。英文全大写 Eyebrow 保持短小并增加字距。

### 4.5 字重与层级

- Hero：600–650；
- 页面标题：600；
- 列表标题和按钮：550–600；
- 正文：400；
- 元数据：400–500。

禁止用极细字重营造高级感。主列表标题、操作和导航在 1280px 截图中必须能直接识别。

### 4.6 间距、圆角与边框

```text
spacing: 4, 8, 12, 16, 24, 32, 48, 64
radius-control: 8px
radius-panel: 10px
radius-major: 12px
border: 1px
```

完整胶囊只用于状态点、头像或非常短的模式切换。区域分隔优先使用 1px Hairline；阴影默认关闭，大型抽屉可使用一次低透明扩散阴影。

### 4.7 动效

- Hover/Focus：120–160ms ease-out；
- 抽屉：180–220ms ease-out；
- Accordion：160–200ms；
- 已知进度使用线性变化，未知进度使用克制 Skeleton；
- 背景线条只允许极慢、几乎不可察觉的运动。

`prefers-reduced-motion: reduce` 下取消位移、背景动画和自动平滑滚动，保留即时状态切换。

## 5. 布局系统

### 5.1 参考视口

- 原型验收：1280 × 720；
- 设计参考：1440 × 1000；
- 内容必须在 1280px 宽完成主要任务，不依赖横向滚动。

### 5.2 普通应用壳层

- 左侧导航：232px 左右，固定；
- 顶部上下文栏：56px；
- 内容区按页面决定最大宽度；
- 管理中心与账号区固定在导航底部；
- 导航行高不低于 44px，图标约 18px，标签 14px。

当前项同时使用背景、左侧标记或边框及文字权重，不只改变颜色。导航图标必须有明确语义和统一笔画风格。

### 5.3 管理中心壳层

管理中心使用独立的 240–260px 一级侧边栏。侧边栏顶部包含品牌与“返回工作台”，其后按 Overview、Content Operations、Pipeline Monitor、Cost Control、Organization 分组。

管理内容区不再次出现普通工作台 Header 或第二条侧边栏。列表和诊断信息以连续区域与细边框组织，不使用彩色 KPI 卡片墙。

### 5.4 内容宽度

| 场景 | 宽度规则 |
|---|---|
| 工作台 | 最大约 1180px，主次两列 |
| 创建研究 | 主表单 760–840px |
| 列表/账本 | 使用可用宽度，列对齐优先 |
| 对话 | 尽量扩大消息纵向与横向阅读区 |
| 报告 | 章节 160–170px + 正文弹性列 + 证据 300–320px |
| 抽屉 | 420–520px，切片或 Trace 可更宽 |

### 5.5 Surface 层级与容器语法

本节定义页面何处使用画布、容器、面板、卡片和列表，是所有业务页面的强制布局输入。组件名称不能自行决定视觉层级；同一个 `Card` 组件不得被当作任意内容的默认包装。

| 层级 | 视觉事实 | 适用内容 | 禁止用法 |
|---|---|---|---|
| `Canvas` 画布 | 使用 `--es-canvas`；无边框、圆角和阴影 | 普通壳层主内容区的最外层背景 | 直接在画布上散放互不关联的白色卡片 |
| `Route Surface` 路由大容器 | 使用 `--es-surface`、1px `--es-border-default`、`--es-radius-major`；不使用阴影 | 工作台、创建研究、各类账本、研究运行态、问答历史、知识库列表与详情 | 用灰色大块替代白色容器；在 Chat、报告或 Admin 上机械套用 |
| `Inset Panel` 内嵌面板 | 使用 `--es-surface-muted`、1px `--es-border-default`、`--es-radius-panel`；不使用阴影 | 启动器、表单主体、摘要条、活动任务、诊断分组 | 与 Route Surface 同为白底造成白卡套白卡；每条列表都做面板 |
| `Action Card` 动作卡片 | 使用 `--es-surface`、1px `--es-border-default`、`--es-radius-panel`；Hover 只改变边框/背景，不抬高阴影 | 具有完整点击目标、独立标题、说明和动作的入口；角色方案等有限实体比较 | 普通数据行、段落、统计数字或装饰性信息卡片化 |
| `Metric Strip` 指标条 | 一个 `Inset Panel` 内以 Hairline 等分；数字、标签与趋势共用一条基线 | 知识库脉冲、管理概览与费用摘要 | 把每个数字拆成彩色 KPI 卡片 |
| `Ledger` 账本/列表 | 继承父表面；列头与数据行使用 Hairline；Hover 使用 `--es-surface-muted`；行本身无圆角、边框和阴影 | 研究任务、知识库、文档、会话、用户、Trace、审计、费用明细 | 一行一卡、瀑布流、只在 Hover 出现关键状态或主操作 |
| `Context Rail` 上下文栏 | 与主列以单条 Hairline 分隔；外层透明且无圆角 | 工作台右栏、创建研究原则、报告章节栏与证据栏 | 为整条右栏再套白色大卡；与主任务争夺视觉主次 |
| `Reader Surface` 阅读器 | 正文连续排版；外层无通用 Route Surface 圆角；段落靠排版和章节间距分组 | 最终报告 | 每个 Claim、段落或章节独立卡片化 |
| `Overlay Surface` 浮层 | Drawer/Dialog/Popover 使用 §6.6 的尺寸、遮罩、阴影和焦点规则 | 登录、上传、来源、切片、Trace、账号与确认 | 用永久右栏代替临时任务；叠加两层遮罩 |
| `Admin Surface` 管理表面 | 独立管理壳层中的连续主区域；分区以 Hairline、Inset Panel 和 Ledger 组织 | `/admin/*` | 嵌套普通应用壳层或再包 Route Surface |
| `Full-bleed` 满幅区域 | 主任务直接占据壳层可用区域，无 Route Surface 外框 | 入口、Chat、报告 | 将普通账本页错误改成满幅灰底 |

层级约束：

- 普通页面必须呈现“灰色 Canvas → 白色 Route Surface → 灰色 Inset Panel/连续 Ledger”的方向；浅色主题下 Route Surface 是页面主体，不能把主体本身做成灰色。
- 一个区域最多出现两层有明确边界的嵌套表面：`Route Surface → Inset Panel → Action Card` 已是上限；第三层内容改用 Hairline、排版或 Accordion。
- 白色 `Action Card` 只允许出现在 `Inset Panel` 或 Canvas 上；放在白色 Route Surface 内时必须有明确的动作边界，不能用作无意义分组。
- 列表默认是 `Ledger`。只有对象本身需要独立比较、整体点击或不同高度内容时，页面规格才能显式批准卡片布局。
- 深色主题保持相同结构和边界数量，只替换 Token 值；不得因深色主题增加发光、渐变或阴影层。

### 5.6 页面 Frame 矩阵

下表直接决定页面最外层容器。后续实现不得从相邻页面推断，也不得用一个全局 `.card` 覆盖这些差异。

| 页面/路由 | Frame | 主列结构 | 主体表面与列表策略 |
|---|---|---|---|
| 入口 `/` | `Full-bleed` | 纵向品牌叙事 | 固定深色，无普通壳层与 Route Surface |
| 工作台 `/workbench` | `Route Surface` | 主列 + 约 315–320px Context Rail | 启动器/活动任务用 Inset Panel；最近记录用 Ledger |
| 创建研究 `/research/new` | `Route Surface` | 表单主列 + 约 280px Context Rail | 表单用 Inset Panel；原则用连续编号列表 |
| 研究任务 `/research` | `Route Surface` | 单列全宽 | 筛选工具栏 + Ledger |
| 研究运行态 `/research/:taskId` | `Route Surface` | 执行主列 + Context Rail | 总进度用 Inset Panel；阶段和事件连续排列 |
| 报告 `/reports/:reportId` | `Reader Surface` | 160–170px 章节 + 正文 + 300–320px Evidence | 正文连续阅读；证据节点才允许卡片 |
| 问答 `/chat` | `Full-bleed` | 单一会话主列 | 消息流连续；来源使用临时 Drawer |
| 问答历史 `/chat/history` | `Route Surface` | 单列全宽 | 筛选工具栏 + Ledger |
| 知识库 `/knowledge-bases` | `Route Surface` | 单列全宽 | 筛选工具栏 + Ledger |
| 知识库详情 `/knowledge-bases/:kbId` | `Route Surface` | 单列全宽 | Metric Strip + 文档 Ledger |
| Admin 总览 `/admin` | `Admin Surface` | 摘要 + 两列运营区 | Metric Strip + 有限诊断面板 |
| Admin 知识库 `/admin/knowledge-bases` | `Admin Surface` | 单列全宽 | 摘要条 + Ledger |
| Admin 文档 `/admin/documents` | `Admin Surface` | 单列全宽 | Metric Strip + Ledger |
| Knowledge Trace `/admin/knowledge-traces` | `Admin Surface` | 单列全宽 | 摘要条 + Trace Ledger + Drawer |
| Research Trace `/admin/research-traces` | `Admin Surface` | 单列全宽 | 摘要条 + Trace Ledger + Drawer |
| 费用 `/admin/billing` | `Admin Surface` | 图表主列 + 费用分解侧列 | Metric Strip + 图表面板 + Ledger，P1 |
| 用户 `/admin/users` | `Admin Surface` | 单列全宽 | 筛选工具栏 + Ledger |
| 角色 `/admin/roles` | `Admin Surface` | 三列角色比较 | 仅此页允许实体 Action Card，P1 只读 |
| 审计 `/admin/audit` | `Admin Surface` | 单列全宽 | 筛选工具栏 + 不可变 Ledger |
| 设置 `/admin/settings` | `Admin Surface` | 三列设置分组 | 分组 Inset Panel + 页面底部动作，P1 |

## 6. 核心组件

### 6.1 Button

按钮分为：

- `Luminous Primary`：高价值创建/进入动作。浅色主题下为深色实底白字；深色主题下为月白底带克制白色渐变光；
- `Ghost`：次级操作。浅色主题下为浅灰填充 + 明确描边；深色主题下为透明底 + 清晰边框；
- `Text`：低风险上下文跳转；
- `Danger`：取消、删除和禁用，仅在明确上下文中使用。

主要按钮高度 40–44px，紧凑按钮 34–36px。按钮必须包含可识别动词，例如“查看报告”“进入现场”“进入知识库”，禁止用低对比小字代替主要操作。按钮必须与所在表面拉开对比：浅色主题下不得使用白色按钮贴白色面板，深色主题下不得使用低亮文字按钮贴深色表面。

状态：Default、Hover、Focus-visible、Pressed、Loading、Disabled。Loading 保留原宽度并显示动作中的文案，不只显示 Spinner。

### 6.2 输入与搜索

输入框浅色主题使用浅灰填充 + 明确描边，深色主题使用暗色填充或透明底加底边；聚焦时显示 moonstone 边框和 2px 外焦点环。Placeholder 只提供格式提示，不代替 Label。

搜索框可带 16px 搜索图标，但品牌 Mark 不使用搜索图标。错误态同时提供错误文本和 `aria-describedby`。

### 6.3 列表与任务账本

知识库、研究任务、问答历史和管理列表共享：

- 11px 表头；
- 15–16px 主标题；
- 11–12px 元数据；
- 34px 明确操作按钮；
- 以 Hairline 分行，不为每行制作悬浮卡片；
- Hover 提升背景 2%–4%，Focus 使用完整可见轮廓。

重要状态不得只在 Hover 时出现。

### 6.4 Status Badge

Badge 使用小型矩形而非大胶囊。包含状态词，并在需要时加图标：

- Ready/Complete：success；
- Processing/Live：spectral cyan；
- Partial/Retry：warning；
- Failed/Canceled：danger；
- Private/Public：中性或 knowledge 色，但必须显示完整文字。

### 6.5 左侧导航

图标和文字保持基线对齐。推荐 18px 图标、14px 标签、46px 行高。品牌区不挤占功能区，底部账号在常见桌面高度仍保持合理间隔，不漂浮到页面中部。

### 6.6 Drawer、Dialog 与 Popover

- Drawer 从右侧进入，用于登录、上传、知识库范围、来源、切片、密码和 Trace；
- Dialog 用于删除、退出、取消等具名确认；
- Popover 用于短暂账号菜单和小型筛选。

Overlay 使用单一暗色遮罩。打开后焦点进入首个有效控件，Escape 关闭非破坏性表面，关闭后焦点返回触发器。Drawer 标题区固定，长内容内部滚动。

### 6.7 可演进知识库选择器

选择器展示搜索、按更新时间倒序的知识库列表、owner、可见性、文档量和选择状态，不把“480 个可检索文档”当成主要范围概念。Research 创建页允许按来源策略多选；Chat v1.0 使用同一视觉语言但只允许单选。

Chat 可以保留未来多选所需的列表宽度和信息层级，但不得显示可操作 Checkbox 或已选数量；多选入口使用禁用状态并附“多知识库问答规划中”说明。Research 列表行点击与 Checkbox 行为一致，键盘可逐项切换；无结果时保留已选项并提供清除搜索。

### 6.8 对话消息

用户消息右对齐，系统消息左对齐。EvidSight 系统消息不显示黑色头像；角色名称使用 14–16px，来源和时间使用 11–12px。

正文宽度以阅读为先，避免知识范围面板和历史栏长期挤压。引用编号为紧凑方形锚点，Hover 和 Focus 明确可点击。

### 6.9 Pipeline Progress

阶段行包含编号、阶段名、动作摘要、耗时和状态。运行态显示七阶段；管理 Trace 可展示业务专属 Phase。状态使用图标+文字。

每个 Phase 的 JSON 在该行下方用 Accordion 展开，标题统一为“查看此 Phase JSON”。JSON 使用等宽字体、语法色克制、可横向滚动，不在最下方提供混合总览 JSON。

### 6.10 Evidence Reference 与 Graph

正文引用使用编号方块。右侧 Evidence Graph 节点展示：

- Evidence 编号和关系；
- 来源标题；
- `internal` 或 `web`；
- 置信/相关度；
- 被使用章节；
- 可访问时的最小片段。

选中态使用 moonstone 边框和极弱光，不使用紫色。`supports`、`contradicts`、`context` 除色彩外还使用文字与符号。Graph 折叠为 42px 左右的恢复栏，恢复按钮始终存在。

### 6.11 Report Reader

报告是编辑阅读界面而非后台详情页：

- 左栏章节紧凑、当前位置明确；
- 正文 16px/1.85，段落宽度适合长阅读；
- 右栏 Evidence Graph 固定在当前视口可用区域；
- Claim 可使用细左线强调，但不能把每段包装成卡片；
- Trace 放在正文末尾独立附录表面，标题明确说明其不是报告结论。

### 6.12 Empty、Skeleton 与 Error

空态使用一句原因、一个示例和一个直接动作。Skeleton 复制最终结构的节奏。错误表面展示：问题摘要、安全错误 ID、有效恢复动作；不展示堆栈或内部路径。

### 6.13 Toast

Toast 用于轻量操作反馈（如主题切换成功），不作为错误主通道——错误仍走表单内错误或 Error Surface。规格：

- 顶部居中固定，`z-index` 高于普通 Overlay；同一时间只显示一条，新反馈替换旧反馈并重置自动消失计时；
- 视觉：`--es-surface` 底、1px `--es-border-default` 描边、`--es-radius-panel` 圆角与 `--es-shadow-floating` 阴影，正文 13px；成功类反馈以 `--es-success` 图标为前缀；
- 语义：`role="status"`，约 2.6 秒自动消失；不承载操作按钮，不替代 Dialog、错误表面或表单校验；
- Toast 不拦截焦点，出现与消失不打断键盘焦点；主题切换确认后焦点仍按 §6.6 返回账号触发器。

## 7. 页面视觉规则

本节逐页定义 1280 × 720 基准视口下的可见结构。页面行为、权限与真实状态仍由 [FRONTEND.md](FRONTEND.md) 定义；本节不允许用尚未实现的后端能力填充视觉空位。

### 7.1 入口 `/`

- 使用固定深色 `Full-bleed` 叙事，不渲染普通应用侧栏、顶部栏、灰色 Canvas 或白色 Route Surface。
- 公共 Header 覆盖在 Hero 顶部：品牌在左，短导航与描边登录动作在右；Hero 标题是第一视觉层，轨道、节点和坐标只做低亮背景。
- 页面按 Hero、信息汇聚、研究过程、证据安全纵向展开；每段靠留白和轨迹连续，不使用营销卡片墙。
- 登录是 460px 左右右侧 Drawer，叠加统一遮罩；关闭后入口页位置不变。入口页不得跟随工作区主题变浅。

### 7.2 工作台 `/workbench`

- 普通壳层内使用单个白色 Route Surface，四周保留浅灰 Canvas；页面标题与欢迎/上下文信息位于容器顶部。
- 内容为主列与约 315–320px 右侧 Context Rail。两列间只有一条纵向 Hairline，右栏不得再包整块白卡。
- 主列顶部“快速开始”是 `Inset Panel`，内部最多两个白色 `Action Card`：快速提问、深度研究。每卡包含图标、标题、说明和明确动作，整卡或按钮命中行为必须一致。
- `RECENT RESEARCH` 是连续 Ledger：标题、状态、更新时间和动作列对齐；无数据时在同一列表区域显示真实空态，不制造统计数字。
- 右栏“活动任务”可使用单个 `Inset Panel`；`RECENT KNOWLEDGE` 紧随其下并使用 Hairline 列表，不增加外层卡片。浅色主题下页面主体必须是白色大容器，不能呈现为整页灰底。

### 7.3 创建研究 `/research/new`

- 使用 Route Surface；标题、简短说明与返回任务列表的次级入口处于首行。
- 主体为弹性表单列 + 约 280px Context Rail。研究问题、来源策略、知识库范围等表单字段放入一个 Inset Panel；字段之间用 24–32px 垂直节奏，不为每个字段建卡。
- 右侧“研究原则/将会发生什么”使用有序编号和 Hairline，外层透明，不与表单争夺视觉重量。
- 主提交动作位于表单末端并与表单内容左边界对齐；禁用、提交中与错误状态保持同一尺寸，不移动布局。

### 7.4 研究任务 `/research`

- 使用 Route Surface；标题与“新建研究”主动作同一标题行对齐。
- 标题下方是筛选 Tab、搜索和必要筛选项组成的单行工具栏；工具栏上下使用 Hairline，不使用工具栏卡片。
- 任务以 Ledger 呈现：研究主题为主标题，状态、来源策略、更新时间和动作保持稳定列宽；长标题最多两行后截断并提供完整可访问名称。
- `进入现场`、`查看报告`按任务状态互斥或并列出现，必须是可见按钮；空态、加载态与错误态占用同一账本区域。

### 7.5 研究运行态 `/research/:taskId`

- 使用 Route Surface；任务标题、状态和取消/查看报告动作组成顶部任务头。
- 总体进度是一个横向 Inset Panel，可包含阶段、连接状态与完成比例，但连接状态和任务业务状态必须分别标注。
- 七阶段 Pipeline 横向或紧凑纵向连续排布；阶段编号、名称、动作摘要、耗时和状态同线对齐，不把每个阶段做成悬浮卡。
- 下方为执行主列 + Context Rail。主列活动流用时间线/Hairline 连续组织；右栏展示任务范围、知识来源与恢复信息。
- 运行态正文保持 14px 以上；在 1280 × 720 首屏至少看见任务头、总进度、阶段概览和活动流开头。

### 7.6 最终报告 `/reports/:reportId`

- 使用 Reader Surface，不套白色圆角 Route Surface。顶部工具栏承载返回、导出和阅读级动作。
- 三栏固定语法：160–170px 章节导航、弹性正文、300–320px Evidence Graph；章节栏和证据栏各以一条 Hairline 与正文分隔。
- 正文标题 38–48px，正文 16px/1.85；章节、段落和 Claim 靠排版与细左线建立层级，不逐段卡片化。
- 引用编号嵌在正文；选中引用只高亮对应正文和 Evidence 节点。置信说明、冲突来源等语义内容可使用 Inset Panel，但不能成为通用信息卡。
- Trace 位于正文末尾的独立附录区域；Evidence 节点允许卡片，因为每个节点是可独立选择的来源对象。

### 7.7 据见问答 `/chat`

- 使用 `Full-bleed` 会话区域，在普通壳层剩余空间内最大化纵向高度，不包 Route Surface 外框。
- 顶部只保留会话标题、单知识库范围与会话级动作；Chat v1 显示单选知识库，不出现多选 Checkbox 或已选数量。
- 消息流为连续阅读区：用户消息可使用右对齐气泡；系统回答左对齐且以正文为主，不为每段回答套大卡。
- Composer 固定在会话区域底部并保留清晰边界；生成、取消、重试不改变输入区宽度。
- 来源详情使用临时右侧 Drawer，知识库选择使用 Popover/Drawer；不得常驻第二侧栏挤压消息正文。

### 7.8 问答历史 `/chat/history`

- 使用 Route Surface；标题与“开始问答”主动作同一标题行。
- 筛选 Tab、搜索与时间筛选组成 Hairline 工具栏；会话使用 Ledger，不使用会话预览卡片。
- 行内展示问题/会话标题、单个知识库名称、消息量、更新时间和进入动作；v1 不显示多知识库数量。
- 空态、加载 Skeleton 和错误态保持列结构，避免状态切换时页面宽度跳动。

### 7.9 知识库列表 `/knowledge-bases`

- 使用 Route Surface；页面标题、范围说明和“创建知识库”主动作构成顶部区。
- 搜索、`all|mine|public` 范围与必要状态筛选位于一条工具栏；筛选结果直接更新下方账本。
- 知识库按 Ledger 行呈现，名称/说明为主列，Owner、可见性、文档数、索引状态、更新时间与动作列对齐；禁止一库一卡。
- 页尾可显示范围/权限说明，但不得用不可验证的全局文档总数作为宣传指标。

### 7.10 知识库详情 `/knowledge-bases/:kbId`

- 使用 Route Surface；顶部显示知识库名称、Owner/可见性、返回入口与上传/治理动作。
- “Knowledge Pulse”是一个等分 Metric Strip，用同一 Inset Panel 承载文档量、Ready/Processing/Failed 等真实摘要；不拆成多个 KPI 卡。
- 文档筛选工具栏与下方 Ledger 连续：文件名为主列，类型、大小、状态、更新时间和动作保持稳定列宽。
- 上传、文档详情和切片原文均使用 Drawer；后台处理中提示位于 Ledger 下方的说明区，不漂浮为告警卡。

### 7.11 Admin 总览 `/admin`

- 使用独立 Admin Surface；左侧 240–260px 管理导航，主区不出现普通工作台顶部栏或第二侧栏。
- 顶部是页面标题、治理状态与必要刷新动作；核心数字放在一个等分 Metric Strip 中，禁止彩色 KPI 卡片墙。
- 下半区可分为近期治理活动与容量/健康两列；诊断面板必须对应可操作的真实对象，数量保持有限。
- 管理信息可以更密集，但正文、表头和操作字号不得小于普通账本对应规格。

### 7.12 Admin 知识库 `/admin/knowledge-bases`

- Admin Surface 内使用标题、治理范围说明、筛选工具栏和连续 Ledger。
- 可在账本上方使用一个摘要条显示总量、公开/私有与异常数；摘要单元以 Hairline 等分。
- 行内展示知识库、Owner、可见性、文档/索引状态、更新时间及治理动作；禁用/删除等破坏性动作进入具名确认 Dialog。

### 7.13 Admin 文档 `/admin/documents`

- Admin Surface 内使用大标题、文档 Metric Strip、筛选工具栏和 Ledger，四者纵向连续。
- 文档行以文件名和所属知识库为主，Owner、摄取状态、大小、更新时间及 Trace 入口列对齐。
- Trace 是明确的行级动作；状态详情或失败原因使用 Drawer，不扩展成行内多层卡片。

### 7.14 Knowledge Trace `/admin/knowledge-traces`

- 标题区明确保留期/治理用途；其下使用单个摘要条与紧凑筛选工具栏。
- Trace Ledger 保持高密度列对齐：Trace ID、对象、阶段、耗时、重试/降级、结果和时间；Trace ID 使用等宽字体。
- 选择一行打开右侧 Trace Drawer，Drawer 内按 Phase Accordion 展开 JSON；主列表不因 Drawer 打开而改变数据列含义。
- 页面强调耗时、失败和恢复，不展示费用口径。

### 7.15 Research Trace `/admin/research-traces`

- 复用 §7.14 的 Admin Trace 骨架，但列事实改为任务、Phase、Step、耗时、重试/降级和结果。
- 七阶段/业务 Phase 名称和状态必须与前端行为规范一致；不得将内部隐藏推理作为视觉内容。
- 右侧 Trace Drawer 显示逐 Phase 输入输出、错误与安全 ID；禁止在页面底部追加混合总览 JSON。

### 7.16 Admin 费用 `/admin/billing`（P1）

- Admin Surface 顶部为四项以内的 Metric Strip；下方采用使用趋势主列 + 费用构成侧列，再接筛选工具栏和费用 Ledger。
- 图表和费用构成可以使用 Inset Panel；柱线颜色只使用语义 Token，并提供文字等价数据。
- 账本列对齐 Token、Provider/模型、金额、归属对象和时间；不得与 Trace 性能诊断混为同一张表。
- 本页仅是视觉演进基线；完整成本账本未进入范围前，不展示伪造金额、结算或导出成功状态。

### 7.17 Admin 用户 `/admin/users`

- Admin Surface 内使用标题、创建/邀请动作、筛选工具栏和用户 Ledger。
- 每行可含紧凑头像，但用户仍是账本行而非人物卡；姓名/账号为主列，角色、状态、最近活动和动作列对齐。
- 禁用、启用和角色变更状态必须有文字，不只靠颜色；破坏性动作使用确认 Dialog。

### 7.18 Admin 角色 `/admin/roles`（P1）

- 本页允许三列角色实体卡，因为角色是需要并排比较的有限模型；每卡按角色名、用途、权限摘要和状态使用相同结构与高度。
- 卡片外不再叠加 Route Surface；底部政策说明用连续 Inset Panel/Hairline。
- v1 仅展示预设角色且只读；没有后端可配置语义时，不出现可用的保存、拖拽权限或“已更新”反馈。

### 7.19 Admin 审计 `/admin/audit`

- Admin Surface 内使用标题、导出入口、筛选工具栏和不可变 Ledger。
- 行内固定展示事件、操作者、对象、安全审计 ID、时间和结果；事件与对象为主要阅读列，ID 使用等宽字体。
- 详情使用 Drawer；审计行不得出现编辑、删除或伪造的回滚动作。导出无后端能力时保持禁用并解释原因。

### 7.20 Admin 设置 `/admin/settings`（P1）

- Admin Surface 内使用标题/最近保存信息、三列设置分组和页面底部动作区；每组是 Inset Panel，字段在组内连续排列。
- 三列用于组织级、管道/保留期和安全类设置；窄屏按 §8 顺序下移，不横向滚动。
- 保存动作必须与真实后端语义绑定；后端未提供读取与持久化时只展示视觉基线或禁用状态，不模拟保存成功。

### 7.21 跨页面 Overlay 状态

| Overlay | 触发页面 | 规格 |
|---|---|---|
| 登录 Drawer | 入口 | 约 460px；浅色；标题/表单固定层级；关闭恢复入口位置与触发焦点 |
| 上传 Drawer | 知识库详情 | 420–520px；文件选择、范围说明、队列和提交状态纵向排列 |
| 来源/切片 Drawer | Chat、知识库详情、报告 | 420–520px，可更宽；先显示来源身份，再显示实时鉴权后的原文或受限态 |
| Trace Drawer | Admin Trace、文档 | 可宽于普通 Drawer；逐 Phase Accordion + 等宽 JSON，内部独立滚动 |
| 知识库选择 Popover/Drawer | Chat、创建研究 | 桌面短列表用 Popover，长列表/窄屏用 Drawer；Chat 单选、Research 按策略多选 |
| 主题选择卡片 | 全局（账号菜单「主题选择」） | 居中选择卡片约 410px：浅色/深色两个选项各带固定色板预览（`--es-swatch-light/dark`，与当前主题无关），当前主题打勾标注；Escape/取消关闭并返回账号触发器 |
| 主题切换确认卡 | 全局（主题选择内） | 约 360px 确认卡片叠加在选择卡片之上（选择卡片保持可见、inert 不参与交互）；取消返回选择卡、确认后应用主题并弹出顶部 Toast（§6.13） |
| 确认 Dialog | 全局 | 只用于具名风险动作；标题、影响说明、取消和确认顺序固定，不承载长表单 |

Overlay 不是独立页面卡片。任何打开态都必须纳入对应页面的 light/dark 视觉验收；不得只验关闭态截图。

## 8. 响应式规则

### 8.1 Desktop：`>= 1200px`

完整侧边栏、顶部栏、报告三栏和右侧抽屉。列表尽量保持列布局。

### 8.2 Tablet：`768px–1199px`

普通侧边栏折叠为图标栏；工作台次列下移；报告 Evidence Graph 默认折叠，章节栏缩窄或转为顶部选择器；管理侧边栏可折叠但仍是一级导航。

### 8.3 Mobile：`< 768px`

导航成为 Drawer；列表转为语义分组行；主要操作固定在可达区域；报告正文单列，章节和 Evidence 分别使用 Sheet；对话输入不被系统键盘遮挡。禁止为了保留桌面表格而制造整页横向滚动。

## 9. 无障碍规范

- 正文和控件达到 WCAG AA；
- 所有交互有清晰 `focus-visible`；
- 点击目标最小 40 × 40px，密集表格中的例外不得低于 32px且需有足够间距；
- 图标按钮必须有可访问名称；
- 状态更新避免逐 Token 朗读；
- 抽屉、Dialog、Accordion、Tab 和 Menu 使用正确语义；
- 引用与 Evidence 联动后将焦点或可感知状态移动到目标，不只视觉滚动；
- 图表和成本柱状图提供文本等价内容；
- 颜色不是唯一信息通道。

## 10. 文案与本地化

- 主要界面使用简体中文；
- Pipeline 阶段、Trace ID、Provider 名可保留英文；
- 按钮使用“动词 + 对象”；
- 失败文案描述用户可见事实和下一步，不推断内部原因；
- 数量、日期、时区和金额通过统一 Formatter 输出；
- 中文与英文/数字之间由排版组件或格式化规则保持一致空隙。

## 11. 实现约束

- Token 通过 CSS Variables 和 Tailwind Theme 映射暴露，业务组件禁止硬编码颜色；
- 组件 Variants 只表达语义，不接受任意颜色参数；
- 页面不得复制粘贴 Button、Badge、Drawer、列表行和状态映射；
- Font、Icon 和噪声资源本地化或有可靠降级，避免关键 UI 因第三方 CDN 失败消失；
- 噪声和渐变不参与命中测试；
- 长列表使用分页或虚拟化，但不得破坏键盘焦点与返回位置；
- 打印/导出报告使用独立浅色打印样式，隐藏应用导航和交互控件。
- 品牌 Mark 的唯一几何参考是 [`resource/prototype/reference/evidsight-web/index-light.html`](../../../resource/prototype/reference/evidsight-web/index-light.html) 中的 `#brand-mark`；生产实现应封装为共享 React 组件，不得用圆点、字符或通用图标替代；
- 导航图标的参考资产是 [`fa-solid-900.woff2`](../../../resource/prototype/reference/evidsight-web/assets/fonts/fa-solid-900.woff2)，生产接入前必须按依赖治理说明用途、维护状态、体积与替代方案，并由统一 Icon 组件封装；
- 交互原型中的旧 Token、Hash 路由、Mock 数据和原生脚本不得复制为生产事实。

## 12. 视觉验收清单

### 12.1 全局

- [ ] 无紫色、洋红或高饱和霓虹；
- [ ] 默认浅色主题：登录抽屉与登录后工作区为浅色，入口叙事页保留品牌深色；
- [ ] 账号菜单「主题选择」两步骤确认（选中 → 确认卡 → 顶部 Toast），确认后生效并持久化，刷新后恢复；
- [ ] 深浅主题正文与辅助文字均满足 WCAG AA，无组件在任一主题下与所在表面同色；
- [ ] 背景包含克制渐变/噪声/线条（深色）或干净浅灰分区（浅色），不是纯黑大平面；
- [ ] 导航文字约 14px、图标约 18px，可直接识别；
- [ ] 主操作是按钮，不是低对比小字；
- [ ] 页面没有无意义卡片化和过量圆角；
- [ ] 页面最外层 Frame 与 §5.6 一致，普通页能清楚看见 Canvas、Route Surface 和内嵌内容三者边界；
- [ ] Surface 嵌套不超过 §5.5 上限；列表行没有被通用 Card 包装；
- [ ] Focus、Hover、Disabled、Loading 状态齐全；
- [ ] 1280px 宽无主要区域冲突。

### 12.2 业务页面

- [ ] 工作台为白色 Route Surface + 主列/Context Rail；快速启动和活动任务是 Inset Panel，最近研究/知识是 Ledger；
- [ ] 创建研究为 Inset Panel 表单 + 透明原则栏；研究任务、问答历史、知识库和 Admin 数据页均保持列对齐 Ledger；
- [ ] 问答无装饰头像，消息角色和来源层级清楚；
- [ ] Research 多知识库选择按 KB 名称检索和勾选；Chat v1.0 仅单选，多选入口不可执行并显示“规划中”；
- [ ] 文档切片可从知识库和回答来源进入；
- [ ] 研究任务与知识库列表按钮规格一致；
- [ ] 报告章节栏不过宽，Evidence Graph 常驻且可恢复；
- [ ] 引用与 Evidence 节点双向选中和定位；
- [ ] Trace 是末尾附录，不与报告结论混合；
- [ ] 管理中心是独立一级壳层；
- [ ] Admin 总览/详情不套普通 Route Surface，Metric Strip 不拆成彩色 KPI 卡片；角色页以外不使用实体卡片墙；
- [ ] Phase JSON 在对应 Phase 内展开；
- [ ] Pipeline Trace 不显示成本，成本页面不伪装成 Trace。

## 13. 原型基线

### 13.1 权威层级

原型截图是完整产品页面结构和视觉方向的基线，不是业务规范替代品。实现可以因真实数据、响应式和无障碍要求调整，但主要信息层级、壳层、动作位置与视觉语义不得无说明偏离。v1.0 只要求实现 `FRONTEND.md` 标记的 P0 页面；P1 原型不得被误解为当前交付承诺。

发生冲突时按以下顺序处理：

1. 业务行为、权限、路由和数据：PRD、FRONTEND、API 与已接受 ADR；
2. 视觉语义和 Design Token：本文；
3. 页面结构、动作位置和品牌资产：跟踪版交互原型；
4. 像素与主题参考：light/dark PNG。

下级来源不得覆盖上级规范。发现冲突时按文档治理流程暂停并裁决，不得选择方便实现的一方。

### 13.2 跟踪版交互原型

正式交互原型位于 [`resource/prototype/reference/evidsight-web/`](../../../resource/prototype/reference/evidsight-web/)，页面映射与 P0/P1 范围以其 [`prototype-manifest.json`](../../../resource/prototype/reference/evidsight-web/prototype-manifest.json) 为准。

- 该目录是设计参考资产，不进入 Vite 构建、部署、生产运行时或 API Consumer；
- React 实现必须复用其主要区域、信息层级、动作位置、排版节奏与品牌资产；不得用通用 SaaS 模板自行重组；
- 原型源码内的业务示例不构成行为授权。Chat 多 KB、P1 Admin、旧 Token 和外部字体等覆盖规则见该目录 README；
- `.superpowers/` 仍是工具临时目录，不是开发输入；生产开发只能引用已跟踪目录；
- 修改原型必须同步检查 manifest、两套 PNG、本文和 FRONTEND，不允许无记录替换视觉目标。

### 13.3 截图与逐切片视觉门禁

原型截图按主题分目录归档，同一页面编号在两套主题下对应：`resource/prototype/dark/`（`01`–`20`，深色主题基线）与 `resource/prototype/light/`（`01`–`20`，浅色默认主题基线）。页面结构、壳层、动作位置以浅色默认版为主基准，深色版提供同一结构下的可选外观；主题切换交互以最新交互原型为准。

视觉验收固定使用 `1280 × 720` CSS px、device scale 1、固定 Chromium、已提交本地字体和确定性 Fixture。每个页面切片必须在生产实现前建立对应视觉 RED，并在完成声明前满足：

- 同一视口、主题、路由、业务状态和数据下分别捕获目标与实现；
- 入口、空态、加载、错误及该切片关键交互态至少各有一个明确验收目标；
- 动画、时间和随机 ID 在截图中冻结；
- 自动截图差异阈值由首次基线评审固定在测试配置中，后续不得为让失败通过而单独放宽；
- 自动差异通过后仍检查字体、布局、裁切、按钮、边框、圆角和品牌资产；截图通过不能替代键盘、焦点和对比度测试；
- 切片 8 负责跨页面完整 E2E，不接管各切片本应完成的视觉回归。

未建立或未通过视觉 RED/GREEN 的页面只能声明“行为已实现，视觉待验收”，不得声明对应前端切片完成。

## 14. 相关文档

- [FRONTEND.md](FRONTEND.md)
- [PRD.md](../../../docs/specs/PRD.md)
- [ARCHITECTURE.md](../../../docs/specs/ARCHITECTURE.md)
- [IDENTITY_AND_ACCESS.md](../../../docs/specs/IDENTITY_AND_ACCESS.md)
- [API.md](../../../docs/specs/API.md)
