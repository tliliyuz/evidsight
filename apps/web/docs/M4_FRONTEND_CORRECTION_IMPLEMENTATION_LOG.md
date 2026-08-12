# M4 前端视觉纠偏实施过程记录

| 属性 | 值 |
|---|---|
| 文档状态 | 实施过程记录（非权威） |
| 记录范围 | 纠偏 3B 知识中心及同期发现的全局前端缺陷 |
| 记录日期 | 2026-08-10—2026-08-11 |
| 当前行为权威来源 | [FRONTEND.md](FRONTEND.md) |
| 当前视觉权威来源 | [UIDESIGN.md](UIDESIGN.md) |

本文保存负责人真机/视觉复核中的发现、候选实现、参数调试和验证轨迹，避免把过程流水写入权威规范或 `docs/CHANGELOG.md`。本文不授权产品行为，不替代 FRONTEND、UIDESIGN、API、PRD 或 ADR；过程描述与当前规范冲突时，以对应权威来源为准。

ADR 检查 1–8：否。本文只重新归档已经发生的前端实施与复核记录，不改变产品行为、服务边界、公共契约、权限模型、数据生命周期或技术机制。

## 1. 记录边界

本轮最初目标是纠偏切片 3B 的两个页面：

- `/knowledge-bases` 知识库列表；
- `/knowledge-bases/:kbId` 知识库详情与文档管理。

复核过程中同时暴露了登录反馈、退出确认、修改密码、全局 Toast 生命周期和退出后 Query 清理等跨页面缺陷。这些缺陷不属于 3B，实施与 Changelog 均按“前端全局身份与会话修复”单独归类，见 §4。

## 2. 初始实现与首轮视觉 GREEN

首轮实现完成了知识中心的基本行为和原型结构投影：

- 权限按当前 `/me` 用户、资源 owner 和管理员治理角色判断；上传只允许 owner，编辑/删除允许 owner 或管理员治理；
- 知识库和文档由悬浮卡片改为连续 Ledger，使用 Hairline 分行并对齐状态、时间和动作列；
- 列表消费后端 `index_status` 与 `owner_username`，不根据分块数量猜测索引状态；
- 详情提供返回、Hero、文档摘要、筛选、分页、上传和切片 Drawer；
- 切片使用稳定 `segment_id` 实时请求原文，撤权或来源失效后立即清除正文；
- 建立知识中心浅色/深色、列表/详情、六状态、Drawer 和权限态的 Playwright 基线。

该轮通过行为测试和截图差异门禁，但负责人真机复核仍发现层级、对齐、密度和反馈问题，因此只能视为“自动化视觉 GREEN”，不能视为负责人视觉验收完成。

## 3. 3B 视觉复核轨迹

### 3.1 工具栏、搜索与空态

- 筛选工具栏增加上下 Hairline，与页面标题和下方 Ledger 分区；
- 搜索改为输入后回车提交，移除多余搜索按钮；
- 切换 `all|mine|public` Scope 时清除名称搜索，避免条件跨范围残留；
- 区分“资源为空”与“筛选无匹配”，后者不重复提供页面头部已有的创建动作；
- 空态和错误态统一居中结构，错误恢复动作使用统一 Primary Button，而非浏览器默认按钮。

### 3.2 动作归属与全局反馈

- 知识库列表操作列只保留“进入知识库”，编辑和删除迁入详情 Hero；
- 删除知识库后从相关列表缓存移除、返回列表并给出全局成功反馈；
- 删除文档、创建/编辑知识库和上传失败统一读取标准错误信封的安全文案；
- 页面局部 Toast 被证明无法覆盖跨路由反馈，后续收敛为根级全局 Provider。该全局基础设施及身份相关反馈不再计入 3B，见 §4。

### 3.3 Route Surface 与分页

- 知识中心接入与工作台共用的 Route Surface，浅灰 Canvas 包围单个白色大容器；
- 容器改为固定视口内高度，Header/工具栏/分页保持稳定，中间 Ledger 独立滚动；
- 分页抽取为共享组件，默认每页 10 条，支持上一页、页码窗口、省略号、下一页和当前页提示；
- 负责人最终手调 Canvas 边距为 `10px 10px 0`，Route Surface 高度为 `calc(100vh - 46px)`；这是验收参数，不是行为规范；
- 固定高度后曾出现 Ledger 单行被 Grid 拉伸到填满剩余高度的回归，最终通过 Ledger body `align-content: start` 恢复内容行高。

### 3.4 主按钮与状态色

- Primary Button 从品牌蓝青底调整为浅色主题近黑底白字、深色主题近白底黑字，并补原型使用的动作箭头；
- Hero 可见性徽章恢复独立色调：公开为 knowledge 蓝，私有为中性灰；
- 文档六状态不再复用模糊色调：queued/deleting 中性灰、processing 青绿、completed success 绿、partial warning、failed danger；
- 状态始终同时展示文字，颜色不作为唯一通道。

### 3.5 详情 Hero

- Hero 从普通左右 Flex 调整为共享行轨道的双列布局：名称与动作同行，描述首行与元数据同行；
- 元数据最终顺序为 `owner 创建 → 可见性 → YYYY-MM-DD HH:mm 更新`；
- 名称单行省略并保留完整可访问名称，描述最多三行且限制正文宽度，避免长内容挤压动作区；
- owner 展示优先使用后端 `owner_username`；当前用户是 owner 且字段缺失时可回退 `/me` 用户名，非 owner 不伪造他人用户名；
- 操作区权限最终保持：上传仅 owner；编辑/删除为 owner 或管理员治理；没有真实 Chat 单 KB 建立语义时不显示“用它提问”假入口。

### 3.6 Knowledge Pulse 与时间口径

- 详情新增单个三等分 Metric Strip，承载文档总数、分块总数和创建时间；数据全部来自知识库响应，不伪造缺失的状态聚合；
- 三格使用一致的展示字体、标签和说明基线，不拆成彩色 KPI 卡片；
- Hero、知识库 Ledger 和文档 Ledger 的时间统一为本地绝对时间 `YYYY-MM-DD HH:mm`，不再混用“刚刚/分钟前”；
- 文档与知识库 Ledger 的“操作”表头对齐右侧动作列。

### 3.7 上传 Drawer

- 原生单文件选择外观改为常驻 Drop Zone；选择文件后 Drop Zone 不消失，队列显示在其下方并允许继续添加；
- 支持 PDF、DOCX、Markdown、TXT，单文件上限 50 MB；同名和非法扩展名文件忽略并提示；
- 批量上传是客户端串行调用既有单文件 API，不新增推测端点；
- 上传中逐文件展示就绪、上传中、完成、失败或取消；取消使用 AbortSignal 中止当前批次，未开始文件标记取消，Drawer 保持打开；
- 任一文件成功后最终选择关闭 Drawer、刷新详情列表，由非终态文档 5 秒轮询继续推进状态；
- Drop Zone 最终最小高度为 200px，Drawer 页脚动作统一居中。

### 3.8 最终复核与基线

- 修复空态/错误态在主区左侧拥挤及错误按钮使用默认样式的问题；
- 统一重建知识中心和受共用容器影响的工作台截图，清理孤儿基线；
- 2026-08-11 再次全量重建 29 张 E2E 基线；缩略全图复核发现登录失败/提交中截图使用 Playwright 默认洋红 Mask 覆盖账号和密码输入框。移除 Mask 后让确定性输入内容、密码掩码、错误提示和忙碌态完整进入视觉验收；
- 最后记录的门禁结果为 Vitest 174 项全绿、ESLint、Prettier、TypeScript/Vite build、Design Token、视觉基线静态门禁通过，Playwright 30 项通过且二次运行稳定；
- 自动截图通过只证明确定性 Fixture 下无基线漂移；负责人真机视觉确认仍是本轮最终视觉验收来源。

## 4. 同期发现但不属于 3B 的前端修复

以下问题从 3B 复核过程中暴露，但作用域是整个前端应用，必须独立跟踪。

### 4.1 登录成功反馈

登录/注册成功后增加全局成功 Toast。初版 Provider 只位于登录后壳层，导致 `/login` 子树调用落到空实现；组件测试因手工包裹 Provider 未发现该真机缺陷。最终将 Toast Provider 提升到根路由布局，使登录页和登录后页面共享同一实例，反馈可以跨导航存活。

### 4.2 退出登录

账号菜单退出动作增加具名确认；确认后才退出，跳转登录入口后仍显示“已退出登录”全局反馈。该流程依赖根级 Toast 生命周期，不属于知识中心页面行为。

### 4.3 修改密码

补齐账号菜单中的修改密码 Drawer：当前密码、新密码、确认新密码、显示密码、前端一致性检查、忙碌态、安全错误映射和成功反馈。接口消费既有 `PUT /api/v1/auth/password`，没有新增后端能力。

### 4.4 Query 与敏感状态清理

退出、Refresh 失败或会话清理时触发统一敏感清理回调，清空受保护 Query 缓存，避免切换账号后残留上一用户的知识库、会话或任务数据。该行为属于 FRONTEND 全局会话边界，不属于 3B。

### 4.5 全局反馈基础设施

知识中心删除、主题切换、登录、退出和改密统一使用根级 Toast；错误仍使用字段错误或 Error Surface。Toast 的当前视觉与可访问性事实见 UIDESIGN §6.13，具体行为见 FRONTEND 对应章节。

## 5. 切片 4 Chat/问答历史视觉复核轨迹（2026-08-12）

本轮范围为切片 4「据见问答/问答历史」的视觉复核。负责人真机对照跟踪版原型 `data-route-view="chat"`/`chat-history`（`resource/prototype/reference/evidsight-web/index.html`）提出六项差异，逐项修正：

1. **页头补「重命名」**：`chat-header-actions` 加 ghost 按钮；无会话（新对话）时禁用；点击打开重命名对话框（`RenameDialog` 从问答历史抽为共享组件 `components/feedback/RenameDialog.tsx`），成功失效 conversation 查询并关闭，失败 toast 且保持打开。
2. **KB 触发器改原型 scope-trigger**：「已选知识库 + 数量徽章」（v1 单选为 0/1，`kb-picker__count`）。所选名称移入页头下方 `scope-summary`（「本对话已选择「X」；每轮提问会重新确认访问权限。」），`?kb=` 进入经 `knowledgeApi.getKnowledgeBase` 解析名称、会话回读用 `kb_name`、会话内新选优先 `selectedKbName`。FRONTEND §5.5「被搜索过滤仍显示真实名称」相应改为由 scope-summary 承载。
3. **引用编号改内联小方块锚点**：由正文下方独立 `ol` 胶囊列表改为 `chat-citation` 24×24 方块锚点（仅编号 01/02/03）内联附于回答正文之后。SSE content 无 claim→source 映射，编号按来源数组顺序整体附于回答尾部、不做逐句归因；文档名由来源卡片（`SourceCards`）承载；保留「按检索相关度排序」说明。
4. **回答底部信息栏**：`answer-foot` 改「使用 N 个知识库 · M 个来源」+ 右侧「复制回答」（`navigator.clipboard.writeText`，点击短暂显示「已复制」；剪贴板不可用时静默失败）。
5. **发送按钮**：深色实底 + 右侧 ↗ 箭头（显式 `chat__composer-send-arrow` span，`::after` 抑制避免 `.btn--primary::after` 重复箭头）。
6. **时间戳**：确认 `formatChatTimestamp` 仅输出本地 `HH:mm`，与原型「EVIDSIGHT · 14:28 / 我 · 14:28」口径一致，无改动。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过；vitest 全量 **211 项**全绿（新增页头重命名、回答底部复制、引用方块锚点等用例；知识库选择器徽章相关断言同步更新）；`chat.spec.ts` 9 项按新布局重建基线通过（含新增 `chat-header-scope-light` 截图）。Playwright 全量 45 项未复跑——负责人要求先人工复核、按「改完即 build」迭代推进，验收稳定后再一次性升格。

### 5.1 第二轮（2026-08-12）侧边栏 / 白容器 / 历史列表

负责人第一轮验收后提出四项全局与历史页问题，逐项修正：

1. **侧边栏选中态沾连**：`/chat`、`/research` 两个 NavLink 加 `end` 精确匹配，避免「据见问答」在 `/chat/history` 下也高亮、「研究任务」在 `/research/new` 下也高亮；「知识库」不加 `end`（详情页 `:kbId` 仍属同一导航项）。
2. **Chat 页白容器**：`.chat` 对齐其它 route-surface 页面（浅灰 Canvas 内单个白色大容器 `max-width:1260px` + 边框圆角，消息流内部滚动、Composer 固定在底部）。注：与 UIDESIGN §7.7「Full-bleed 会话区域」存在取舍，以负责人本轮指示为准，记录于此待后续收敛权威文档。
3. **问答历史列表**：复用知识库列表模式——`.list-toolbar`（上下 Hairline）：左侧 segmented 时间分类「全部/今天/本周」+ 右侧搜索输入与更新时间排序；Ledger 改固定视口高度内滚动（列头固定、行区内滚、分页固定在底部）。「今天/本周」目前按 `last_message_at` 对服务端返回的当前页做前端筛选；后端列表接口暂无时间范围参数，分类计数与分页仍按「全部」口径，需要精确分类统计时须后端支持（记录待裁决）。
4. **行操作收敛**：行内只留主操作「打开对话」；「重命名/删除」收敛到 `⋮` 溢出菜单（新增共享组件 `components/overlay/RowMenu.tsx`，点击外部/Escape 关闭），对齐知识库列表「操作列只留主操作、次级操作不挤列」的处理。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过；vitest 全量 **212 项**（新增时间分类筛选、行菜单动作用例，行操作断言改为先开菜单）；ESLint/Prettier/Design Token 通过。Playwright 未复跑（负责人要求先人工复核、按「改完即 build」迭代）。

### 5.2 第三轮（2026-08-12）新对话页：Composer / 页头 / 空态 / KB 选择器

负责人提出新对话页四项视觉问题，逐项修正：

1. **Composer 去框 + 深度思考开关**：去掉输入区的边框矩形盒（`chat__composer` 去 border/background，textarea 仅保留底部分隔线），聚焦时 `outline:none` 只保留文本光标；删除「回车发送 · Shift+回车 换行」提示，改为底栏左侧「深度思考」开关按钮（`chat__composer-deep`，前端 `aria-pressed` 状态；后端思考模式落地前为纯前端开关，记录待接入）。
2. **页头结构**：「← 问答历史」由无边界文字链接改为有边界按钮（`history-trigger`）；删除「据见问答」eyebrow；会话标题与返回按钮同一行基线对齐；`scope-summary` 移入左列（`chat-header__main`）位于标题正下方，不再横跨到右侧动作区。
3. **空会话留白**：空态由单行提示改为「提示 + 一键问答提示词」三枚胶囊（`QUESTION_PROMPTS`，点击预填输入框），消除输入区与提示之间的大片留白。
4. **KB 选择器**：修复弹层把容器往右挤的 bug（面板改 `right:0` 右对齐 + `width:min(360px,…)` 窄化）；新增「全部/我的知识库/公共知识库」作用域选中栏（复用 `segmented`，`pickerScope` 并入 queryKey）；`page_size` 由 20 收敛到 5（每类最多平铺 5 条、服务端按更新时间倒序）。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过；vitest 全量 **212 项**；ESLint/Prettier 通过。Playwright 未复跑（待负责人验收后统一重建基线）。

负责人复核修正三点（同日）：① 前一轮误删了 Composer 外框——「蓝色输入框」指聚焦时出现的蓝色焦点环而非外层大框，已恢复 `.chat__composer` 外框（border/radius/背景），并让 textarea 聚焦仅保留文本光标（`:focus`/`:focus-visible` 均 `outline:none`）；② 空会话态加问候语「你好，我是 EvidSight，有什么我能帮你的吗？」，提示词由一行三个改为 3-2-1 倒三角（`QUESTION_PROMPT_ROWS`，每行独立 `chat__prompt-row` 居中）；③ scope-summary 归位——由 `chat-header__main` 直下改为包进 `chat-title-col`（与标题同一列，左缘对齐标题而非落到返回按钮下方）。

### 5.3 第四轮（2026-08-12）空态提示 / 输入框高度 / KB 选中态 / 去掉平铺来源

负责人复核四点，逐项修正：

1. **空态提示归位**：「请先选择知识库，再开始问答。」由空态区居中改为放在页头「已选知识库」触发器旁边（`chat-header__kb-hint`，仅未选知识库时显示）；空态区只留问候语 + 倒三角提示词。
2. **输入框高度**：`.chat__composer textarea` 增加 `min-height:44px`，不低于下方发送按钮高度（此前单行 rows=1 比按钮矮）。
3. **KB 选中态被裁剪**：`.kb-picker__option[aria-selected='true']` 由 `outline` 改为 `box-shadow: inset 0 0 0 2px var(--es-focus)` + `--es-moonstone-soft` 底色——outline 在滚动容器内被裁剪导致蓝色边框显示不全，inset 边框不被裁剪。
4. **去掉平铺来源卡片**：`ChatAnswer` 移除 `SourceCards`（回答页不再平铺来源），来源只通过点击正文引用序号锚点打开右侧来源详情抽屉主动查看；删除 `SourceCards.tsx`（仅 ChatAnswer 使用，已无引用）。对应单测/e2e 断言同步改为「引用锚点 → 抽屉」路径。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过；vitest 全量 **215 项**；ESLint/Prettier 通过。Playwright 未复跑（待负责人验收后统一重建基线）。

### 5.4 第五轮（2026-08-12）问候语强调 / 孤儿会话 / 重命名弹窗 / 滚动条间距 / 重命名按钮

负责人复核五点，逐项修正：

1. **问候语强调**：`.chat__empty-greeting` 加粗（`font-weight:600`）+ 颜色升到 `--es-ink-primary`，与下方提示词区分。
2. **孤儿会话处理**：`conversation.kb_status !== 'active'`（deleted/unavailable）时，在输入框上方展示警示条「这个会话的知识库已被删除或暂无权限，请选择其他知识库继续提问。」（`.chat__orphan-warning`，`role="alert"`）并禁用发送（`canSend` 与 `orphanConversation` 取反）；用户重新选择知识库后（`?conversation=` 清除）警示自动消失。
3. **重命名弹窗间距**：`.dialog__actions` 增加 `margin-top:20px`，取消/保存按钮不再与输入框挤在一起（RenameDialog/ConfirmDialog 共用修复）。
4. **消息流滚动条与用户气泡**：`.chat__thread` 右侧 padding 由 4px 增至 14px，右对齐的用户气泡/时间戳不再贴到滚动条。
5. **问答页重命名按钮**：由 `variant="ghost"`（无边框文字）改为默认 `variant`（有边界按钮），与「← 问答历史」按钮一致。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过；vitest 全量 **216 项**（新增孤儿会话警示用例）；ESLint/Prettier 通过。Playwright 未复跑（待负责人验收后统一重建基线）。

### 5.5 第六轮（2026-08-12）markdown 渲染 / 品牌提示词 / 来源定位

负责人复核后提出后端品牌名、回答 markdown 渲染与来源页码问题，逐项修正：

1. **后端品牌提示词 DocMind → EvidSight**：`sse_stream.py::_META_RESPONSE`（Chat meta 固定回复）与 `rag/knowledge_pipeline.py::CASUAL_SYSTEM_PROMPT` 两处。后端无 markitdown——文档解析用 `pymupdf`+`pdfplumber`（PDF）+ `python-docx`（DOCX，标题转 `#`），`markdown-it-py` 仅作 md 解析；docx 的 `page` 字段实为段落序号（技术债）。
2. **回答正文 markdown 渲染**：接入 `react-markdown@10`（新增前端依赖，替代此前手写轻量渲染器；负责人在场确认）。后端注入的 `[来源N]` 标记预处理为 `#cite-N` 链接占位，由自定义 `a` 组件拦截渲染为内联引用按钮（点击打开来源详情抽屉）；内容含内联标记时不再额外渲染正文下方来源条，无标记时保留来源条兜底。
3. **来源定位 PDF=页 / 其它=段**：`chatFormat.sourceLocation` 按 `doc_name` 扩展名区分——`.pdf` 显示「第 X 页」，docx/md/txt 显示「第 X 段」，落实 PDF 真实页码、其余为段落序号的技术债。

验证（自动化 GREEN，非负责人验收）：后端 `test_knowledge_pipeline` 7 项通过（`test_chat_generation_service` 的 `doc_uuid_map` 失败为 CHANGELOG 已注明的既有 fixture 漂移，与本次无关）；前端 `pnpm build` 通过、vitest 全量 **222 项**（新增 `chat-markdown.test.tsx` 6 项：内联标记识别/粗体/列表/引用按钮/定位页段）、ESLint/Prettier 通过。Playwright 未复跑。

### 5.6 第七轮（2026-08-12）历史 Ledger 列对齐

负责人反馈「对话/知识库/消息/最近更新/操作」列头与列表行未对齐。用 Playwright probe 实测（1280×720、overlay 滚动条）确认：行与表头列模板/内边距本就一致，唯一缺口是「操作」列头左对齐（知识账本 `.ledger__head span:last-child{justify-self:end}` 已处理，对话账本漏了），且表头与行分属不同滚动上下文（表头在容器外、行在 `overflow-y:auto` 的列表内，经典滚动条下会差一个滚动条宽）。修复：① `.conversation-columns span:last-child` 补 `justify-self:end`，操作列头右缘与按钮列右缘对齐；② 重构 `.conversation-ledger` 为统一滚动容器（`overflow-y:auto` + `scrollbar-gutter:stable`），`.conversation-columns` 改 `position:sticky; top:0` + 白底，表头与行同处一个滚动上下文，任意滚动条模式下列对齐一致。probe 复测：前 4 列 x 完全一致，第 5 列右缘对齐。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过、vitest 全量 **222 项**、ESLint/Prettier 通过。

### 5.7 第八轮（2026-08-12）共享模式收口：chat 页复用 route-surface

负责人指出 3B 与切片 4 大量是同一问题反复出现，要求停止重造。审计确认根因：3B 确立的共享视觉模式（白卡片 route-surface、Ledger、行操作收敛、segmented、固定高度内滚）在切片 4 各自复制/重造而非复用共享类。本轮收口：

- **chat 页白卡片复用共享类**：`ChatPage` main 由 `<main class="chat">` 改为 `<main class="chat route-surface">`，删除 `.chat` 里复制的白卡片 CSS（width/max-width/margin/padding/border/radius/bg/height/overflow），`.chat` 只留 `gap:16px` 聊天区特有间距。probe 实测：chatBg `#ffffff`、线程内部滚动、composer 底部 719px，与其它 route-surface 页一致。
- **行操作收敛**（前几轮已完成）：问答历史用共享 `RowMenu`（⋮ 溢出菜单），对齐知识列表「操作列只留主操作」。
- **列对齐**（上一轮已完成）：对话账本补 `justify-self:end` + sticky 统一滚动上下文，对齐知识 Ledger。

**待收敛项（不属本轮）**：chat 历史 Ledger 用自定义 `conversation-ledger`/`conversation-row` 类而非共享 `.ledger`/`.ledger__row`（视觉已一致，类未复用，列模板不同）；后续页面新增列表时优先复用 UIDESIGN §6 共享组件，不再新造账本类。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过、vitest 全量 **222 项**、ESLint/Prettier 通过。

### 5.8 第九轮（2026-08-12）共享 Ledger 复用：问答历史切到共享 .ledger

负责人指出列表页反复出问题、要求复用共享模式。收口共享 Ledger：

1. **共享 `.ledger` 统一为 sticky 表头 + 单滚动容器**：`.ledger` 由 `margin-top:8px` 改为 `flex:1; min-height:0; overflow-y:auto; scrollbar-gutter:stable`；`.ledger__head` 加 `position:sticky; top:0; background`；新增 `.ledger__head span:last-child{justify-self:end}` 通用操作列头右对齐；新增 `.ledger__cell` 基础样式（min-width/color/font-size）。删除 `.kb-page .ledger` 的 grid 行结构 + `.ledger__body` 滚动覆盖。
2. **问答历史改用共享 `.ledger` 类**：`ConversationHistoryPage` 由 `conversation-ledger/conversation-columns/conversation-list/conversation-row` 改为 `.ledger/.ledger__head/.ledger__body/.ledger__row`，新增 `chat-history-ledger` 列模板修饰（5 列）+ 紧凑行动作 `.ledger__cell--actions .btn`；删除全部自定义 `conversation-*` Ledger CSS。

probe 实测：知识库列表与问答历史均 `ledger` 单滚动 + sticky 表头，前 N 列精确对齐、末列右缘对齐。此轮后知识库 Ledger 基线（3B 时 head 外置 + body 滚动）结构变化，视觉应几乎一致，待统一 e2e 重建基线时确认。

验证（自动化 GREEN，非负责人验收）：`pnpm build` 通过、vitest 全量 **222 项**、ESLint/Prettier 通过。Playwright 未复跑。

## 6. 文档收敛结果

- FRONTEND 只保留当前行为、权限、状态、失败语义和可执行验收条件；
- UIDESIGN 只保留当前视觉层级、Frame、对齐、尺寸和组件语义；
- 本文保存 CSS 类、参数调试、先后推翻关系、真机发现和历轮验证数字；
- CHANGELOG 将 3B 记录合并为一个最终结果条目，并将 §4 的内容拆成“前端全局身份与会话修复”条目；
- 后续视觉纠偏应先在实施过程记录中收集负责人裁决，页面验收稳定后再一次性升格当前事实，避免每轮复核都改写权威规范和 Changelog。

## 7. 相关文档

- [FRONTEND.md](FRONTEND.md)
- [UIDESIGN.md](UIDESIGN.md)
- [跟踪版原型 manifest](../../../resource/prototype/reference/evidsight-web/prototype-manifest.json)
- [CHANGELOG](../../../docs/CHANGELOG.md)
- [文档治理指南](../../../docs/guides/DOCUMENT_GOVERNANCE.md)
