# EvidSight Web Design System — Prototype Baseline

## Product context

EvidSight（据见）是一套面向企业用户的统一知识问答与深度研究工作台。它把内部知识库、公开网络来源、长任务执行过程、研究报告和可追溯证据整合到一个应用中。

第一版原型验证登录后的统一工作台及研究主路径，不复刻旧 DocMind / ResearchMind 的视觉：

- 工作台：快速提问、开始研究、最近研究任务、常用知识库；
- 据见问答：多知识库选择、流式答案、引用来源；
- 深度研究：研究主题、任务类型、knowledge/web/hybrid 来源策略；
- 任务执行：七阶段进度、可理解的步骤事件、取消与断线恢复状态；
- 报告阅读：文章、章节导航、Claim 与 Evidence 侧边面板；
- 管理入口：仅作为全局导航能力出现，第一轮不展开管理页面。

目标平台是桌面优先的响应式 Web 应用。主要用户是需要研究、分析和决策支持的企业知识工作者，不是开发运维人员。

## Experience principles

1. **先工作，后统计**：工作台首先提供提问和创建研究的直接入口，不使用一排无意义 KPI 卡片占据首屏。
2. **证据始终可达**：答案、报告和关键结论的来源均可在当前上下文中展开，不迫使用户跳离工作流。
3. **长任务可理解**：展示阶段、已完成工作、等待与错误；不展示模型隐藏思维链。
4. **两类实时交互不混淆**：Chat SSE 是当前请求流，断开可终止；Research SSE 是持久任务订阅，离开页面仍继续。
5. **克制且精确**：视觉像研究编辑台与现代专业工具，不像聊天机器人、传统后台模板或营销落地页。

## Visual direction

The visual language is **Quiet Intelligence / Premium Research Instrument**:

- cool porcelain or deep midnight foundations rather than natural, cream or green tones;
- obsidian navy carries structure; moonstone blue and spectral cyan appear only as precise signals;
- a quiet sense of depth from tonal layering, translucent overlays and extremely restrained ambient light;
- editorial hierarchy for questions and reports;
- monospaced labels for status, phase, source and timestamps;
- modern geometry with clean negative space, 8–12px control radii and crisp one-pixel borders;
- an original brand mark that evokes an aperture, an eye and converging evidence nodes without literally drawing a magnifying glass.

Do not use nature-inspired colors, green as the brand color, generic SaaS KPI cards, large fluffy Bento cards, exaggerated glassmorphism, loud neon, oversized landing-page typography, or excessive pills. Premium means precision and restraint, not ornament.

### Midnight atmosphere

The dark direction must not use a flat solid-color page background. Build restrained depth with CSS-only layers:

- a midnight-to-obsidian radial gradient centered slightly above and right of the primary composer;
- a second very low-opacity cool teal radial haze near the lower-left edge;
- a fine monochrome noise texture at roughly 2–3% opacity, created with an inline SVG `feTurbulence` data URI or an equivalent CSS texture;
- an optional sparse one-pixel coordinate grid fading toward the page edges.

The texture must remain almost subconscious and must not reduce text contrast. Do not use purple, bright aurora gradients, animated star fields, lens flares or visible cyberpunk neon.

## Color tokens

- `--porcelain: #F5F6F8` — light app canvas
- `--surface: #FFFFFF` — primary reading and input surface
- `--surface-muted: #ECEEF3` — secondary panel and hover state
- `--midnight: #090B12` — dark shell or full dark foundation
- `--obsidian: #111522` — elevated dark surface
- `--ink: #151824` — light-theme primary text
- `--ink-inverse: #F4F5F8` — dark-theme primary text
- `--ink-muted: #717789` — secondary text
- `--moonstone: #A9C7D8` — primary brand action and selected signal on dark surfaces
- `--moonstone-hover: #C2D9E5`
- `--moonstone-soft: rgba(169, 199, 216, 0.12)`
- `--spectral-cyan: #70D3D0` — evidence and live-system signal, used sparingly
- `--grid-light: rgba(21, 24, 36, 0.12)` — light hairline divider
- `--grid-dark: rgba(244, 245, 248, 0.12)` — dark hairline divider
- `--danger: #E7677A` — error and canceled
- `--success: #54C99A` — completed
- `--warning: #D8A84E` — partial and warning
- `--knowledge: #6E8FE8` — internal knowledge channel

Purple, violet and magenta are forbidden in the final dark direction. Text and controls must meet WCAG AA contrast. Never use accent color alone to communicate status.

## Typography

- UI and editorial headings: `Space Grotesk`, fallback `Inter, system-ui, sans-serif`.
- Body and report reading: `Inter`, fallback `system-ui, sans-serif`.
- Metadata, phases, source labels and timestamps: `JetBrains Mono`, fallback `ui-monospace, monospace`.
- App title: 24–32px; page title: 28–40px; report title: 36–48px; body: 14–16px; metadata: 10–12px.
- Use tight heading tracking and generous report line height. Uppercase monospaced labels are reserved for short metadata, never paragraphs.

## Layout

- Desktop reference viewport: 1440 × 1000.
- Persistent left rail: 232px expanded, containing brand, five main destinations and account area.
- Top context bar inside content: 56px, with breadcrumb/current context, command/search trigger, notifications and task activity.
- Content max width is contextual: workbench 1180px; form 800px; report article 760px plus navigation/evidence rails.
- Use 1px dividers to create explicit regions. Prefer adjoining panels and a few carefully layered surfaces over a collection of floating cards.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64px.
- Radius: 8px for controls and compact panels; 12px maximum for the primary composer or major overlay. Fully rounded shape is allowed only for avatar, status dot or compact mode switch.
- Shadows are normally absent. A major floating overlay may use one diffuse low-opacity shadow. Never apply a shadow to every card.

## Brand mark

Do not use an off-the-shelf magnifying glass, search-check, brain, sparkles or database icon as the primary brand mark. Construct a recognizable inline SVG mark from simple geometry:

- an asymmetrical hexagonal aperture or broken orbital ring;
- three small evidence nodes converging toward one central sight point;
- one deliberate opening in the outer shape, implying discovery rather than surveillance;
- readable at 24px and distinctive in monochrome;
- primary form uses porcelain or moonstone on dark surfaces, with spectral cyan allowed on one node only.

Pair the mark with a clean `EvidSight` wordmark. Do not place the icon inside a generic colored square.

## Global application shell

Left navigation destinations:

1. 工作台 `/`
2. 据见问答 `/chat`
3. 知识库 `/knowledge-bases`
4. 深度研究 `/research/new`
5. 研究历史 `/research`

Admin users receive a separated 管理中心 entry near the lower rail. The shell must visibly distinguish current location without relying on color alone. A compact “running tasks” indicator stays available globally.

## Unified workbench

The default screen is an action-oriented workspace, not analytics:

- greeting and one concise context sentence;
- one prominent composer with two modes: 快速提问 / 深度研究;
- mode-specific controls appear inside the same composition surface;
- three recent research tasks shown as slim rows with status, phase, source strategy, update time and progress;
- frequently used or recently updated knowledge bases shown as compact rows;
- one restrained “continue where you left off” area when a running task exists.

Avoid a dashboard made from disconnected cards. Use a structured two-column editorial grid: primary creation/activity region and secondary knowledge/context region.

## Core components

### Primary composer

A precisely layered writing surface with a clear textarea, mode switch and contextual control row. Primary action is moonstone with dark text and restrained hover feedback. Knowledge-base picker supports multiple selections. Source strategy is a three-option segmented control (`内部知识`, `公开网络`, `混合研究`) with short explanatory copy.

### Task row

A full-width row separated by hairlines. Show topic, status with icon and text, current phase, elapsed/update time, source channel markers, and progress. Entire row is clickable with a visible focus state. Do not hide important state behind hover.

### Pipeline progress

Display seven phases in sequence: Planning, Searching, Fetching, Reranking, Synthesizing, Evidence Graph, Rendering. Knowledge-only tasks visibly mark Fetching as skipped. Each phase has icon + label + state, not color alone. Detailed steps use plain-language summaries; never expose hidden chain-of-thought.

### Evidence reference

Inline citation markers are compact numbered squares. Selecting one opens a right evidence rail containing title, source type, locator, excerpt where authorized, retrieval time and open-source action. If current knowledge-base permission is absent, retain citation metadata but replace protected excerpt with a permission message.

### Report reader

Three-region desktop layout: compact section navigation, central article, collapsible evidence rail. Claims with support have a subtle left rule and inline references. Partial reports include a permanent disclosed-limitations section, not a dismissible warning only.

## State and feedback

- Loading: skeleton lines matching final structure, not generic spinners for whole pages.
- Streaming chat: cursor and explicit stop control; partial output must not look completed.
- Research reconnecting: persistent top-context status, task continues in background.
- Empty states: provide one direct next action and a short example.
- Error states: plain-language summary, stable error identifier where useful, and only valid recovery actions.
- Destructive actions: explicit confirmation with named target.
- Motion: 120–180ms ease-out for panel/focus transitions; linear progress where actual progress is known. Respect reduced-motion preferences.

## Responsive behavior

- Desktop is primary.
- At tablet width, left rail collapses to icons and the secondary column moves below the primary region.
- At mobile width, navigation becomes a drawer; report section navigation and evidence rail become separate sheets. Primary actions remain reachable without horizontal scrolling.

## Prototype constraints

- Chinese UI copy with occasional English technical phase names only where useful.
- Use realistic example content for an enterprise competitive analysis task.
- Prototype interactions should demonstrate composer mode switching, source-strategy selection, navigation selection, task progress drill-in, and evidence-panel opening.
- The first generated draft should show the default unified workbench at desktop size.
- Use ONLY the fonts, colors, spacing, and component styles defined here. Do not introduce any fonts, colors, gradients, shadows, or visual styles not in this design system.
