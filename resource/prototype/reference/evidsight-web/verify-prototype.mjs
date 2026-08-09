import { readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';

const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const js = readFileSync(new URL('./app.js', import.meta.url), 'utf8');
const iterationCss = readFileSync(new URL('./iteration.css', import.meta.url), 'utf8');

for (const view of ['knowledge', 'knowledge-detail', 'chat', 'chat-history', 'research-create', 'research-tasks', 'research', 'report', 'admin']) {
  assert.match(html, new RegExp(`data-route-view=["']${view}["']`), `missing ${view} route view`);
}

for (const action of ['open-kb-scope', 'close-kb-scope', 'open-chunks', 'close-chunks', 'toggle-adjacent-chunks']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']`), `missing ${action} control`);
  assert.match(js, new RegExp(`['"]${action}['"]`), `missing ${action} behavior`);
}

assert.doesNotMatch(html, /class="conversation-rail"/, 'chat history must not remain a persistent second sidebar');
assert.doesNotMatch(html, /class="chat-history-drawer"/, 'chat history must not use a drawer');
assert.match(html, /data-route="chat-history"/, 'chat history must be a first-level navigation destination');
assert.match(html, /class="conversation-ledger"/, 'chat history must use an independent searchable ledger');
assert.match(html, /class="kb-scope-popover"/, 'multi-KB selection must use a compact popover');
assert.match(html, /id="chat-kb-search"/, 'multi-KB selection needs a search field');
assert.ok((html.match(/data-chat-kb-kind=/g) || []).length >= 4, 'multi-KB selection needs realistic KB rows');
assert.match(html, /data-chat-kb-filter="mine"/, 'multi-KB selection needs a mine filter');
assert.match(html, /data-chat-kb-filter="public"/, 'multi-KB selection needs a public filter');
assert.match(html, /data-route="research-create"[^>]*>[^<]*<i[^>]*fa-microscope[^>]*><\/i>深度研究/, 'deep research navigation must lead to creation');
assert.match(html, /data-route="research-tasks"[^>]*>[^<]*<i[^>]*fa-list-check[^>]*><\/i>研究任务/, 'task list navigation must be explicit');
assert.match(html, /class="message user-message message-right"/, 'user messages must align right');
assert.match(html, /class="message assistant-message message-left"/, 'assistant messages must align left');
assert.doesNotMatch(html, /assistant-sign[^>]*>\s*<svg/, 'assistant messages must not show an avatar');
assert.match(html, /class="message-role"[^>]*>EVIDSIGHT/, 'assistant messages need a clear text role label');

for (const action of ['open-upload', 'close-upload', 'start-upload', 'open-chat-source', 'close-chat-source']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']`), `missing ${action} control`);
  assert.match(js, new RegExp(`['"]${action}['"]`), `missing ${action} behavior`);
}

assert.ok((html.match(/class="scope-option"/g) || []).length >= 3, 'missing multi-KB scope options');
assert.match(html, /class="chunk-drawer"/, 'knowledge documents need a chunk viewer');
assert.match(html, /CHUNK #184|切片 #184/, 'source panel must expose the cited chunk number');
assert.match(html, /相邻切片/, 'source panel must expose adjacent chunks');
for (const section of ['summary', 'matrix', 'findings', 'risks', 'recommendations', 'trace-summary']) {
  assert.match(html, new RegExp(`id=["']${section}["']`), `report missing ${section} section`);
}
assert.match(html, /queued|等待入库/, 'missing queued document state');
assert.match(html, /processing|处理中/, 'missing processing document state');
assert.match(html, /completed|已完成/, 'missing completed document state');
assert.match(html, /partial|部分完成/, 'missing partial document state');
assert.match(html, /failed|处理失败/, 'missing failed document state');
assert.equal((html.match(/class="app-sidebar"/g) || []).length, 1, 'prototype must keep exactly one app sidebar');

assert.ok((html.match(/class="nav-icon fa-solid/g) || []).length >= 6, 'sidebar must use recognizable library icons');
assert.match(iterationCss, /\.app-nav a[^}]*font-size:\s*14px/s, 'sidebar navigation labels must be readable');
assert.match(iterationCss, /\.nav-icon[^}]*font-size:\s*18px/s, 'sidebar icons must be at least 18px');
assert.match(iterationCss, /\.sidebar-bottom[^}]*margin-top:\s*auto/s, 'management and account must remain bottom anchored');
assert.ok((html.match(/\brow-cta\b/g) || []).length >= 10, 'task, knowledge and conversation rows need explicit CTA buttons');
assert.match(iterationCss, /\.archive-columns[^}]*font-size:\s*11px/s, 'knowledge table headers must be readable');
assert.match(iterationCss, /\.research-task-columns[^}]*font-size:\s*11px/s, 'research table headers must be readable');

assert.match(html, /class="[^"]*evidence-graph/, 'report needs a persistent evidence graph');
assert.ok((html.match(/\bevidence-node\b/g) || []).length >= 4, 'evidence graph needs multiple source nodes');
assert.match(js, /scrollIntoView/, 'citation selection must locate evidence anchors');
assert.match(js, /data-evidence-node/, 'evidence nodes must link back to report citations');
assert.ok((html.match(/data-report-section=/g) || []).length >= 6, 'report chapter rail needs internal scroll controls');
assert.match(js, /setActiveReportSection/, 'report chapter rail must track citation-driven navigation');
assert.match(iterationCss, /\.report-layout[^}]*grid-template-columns:\s*170px\s+minmax\(0,\s*1fr\)\s+320px/s, 'report must use a narrow chapter rail and persistent 320px evidence graph');
assert.match(iterationCss, /\.report-article p[^}]*font-size:\s*16px/s, 'report body must use readable 16px text');
assert.match(html, /id="trace-summary"/, 'report must expose a visible trace summary chapter');
assert.ok(html.indexOf('id="summary"') < html.indexOf('id="trace-summary"'), 'report body must begin with conclusions before trace');
assert.ok(html.indexOf('id="recommendations"') < html.indexOf('id="trace-summary"'), 'trace must appear after the report conclusions');
assert.doesNotMatch(html, /data-report-section="methodology"/, 'methodology must be merged into trace instead of occupying a chapter');
assert.doesNotMatch(html, /data-report-section="limitations"/, 'limitations must be merged into trace instead of occupying a chapter');
assert.match(html, /附录 · Trace/, 'trace needs an explicit appendix marker');
assert.match(html, /不属于报告正文结论/, 'trace must be visually and verbally distinguished from conclusions');
assert.ok((html.match(/class="trace-stage/g) || []).length >= 5, 'trace summary needs five auditable research stages');
assert.match(html, /只显示动作、范围与结果/, 'trace summary must explain that hidden reasoning is not exposed');
for (const action of ['toggle-trace-stage', 'locate-trace-evidence', 'locate-trace-section']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']`), `missing ${action} control`);
  assert.match(js, new RegExp(`["']${action}["']`), `missing ${action} behavior`);
}
assert.match(iterationCss, /\.trace-stage\.open/s, 'expanded trace stage needs a visible state');
assert.match(iterationCss, /\.pipeline li b[^}]*font-size:\s*14px/s, 'research runtime phase titles must be readable');
assert.match(iterationCss, /\.activity-stream \.event b[^}]*font-size:\s*14px/s, 'research runtime activity titles must be readable');
assert.match(iterationCss, /\.activity-stream \.event p[^}]*font-size:\s*12px/s, 'research runtime activity body must be readable');
assert.match(iterationCss, /\.task-copy b[^}]*font-size:\s*14px/s, 'workbench recent research titles must be readable');
assert.match(iterationCss, /\.knowledge-quick b[^}]*font-size:\s*14px/s, 'workbench recent knowledge titles must be readable');
for (const action of ['toggle-account-menu', 'open-password', 'close-password', 'submit-password', 'open-logout', 'close-logout', 'confirm-logout', 'open-theme', 'close-theme', 'pick-theme', 'close-theme-confirm', 'confirm-theme']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']`), `missing ${action} control`);
  assert.match(js, new RegExp(`['"]${action}['"]`), `missing ${action} behavior`);
}
assert.match(html, /class="account-menu"/, 'account actions need a compact anchored menu');
assert.match(html, /id="theme-dialog"/, 'theme switch needs a selection dialog');
assert.match(html, /id="theme-confirm"/, 'theme switch needs a confirmation dialog');
assert.ok((html.match(/data-theme-choice=/g) || []).length >= 2, 'theme dialog needs light and dark options');
assert.match(js, /evidsight-theme/, 'theme choice must be persisted');
assert.match(js, /light-theme/, 'theme switch must toggle the light stylesheet');
assert.match(html, /class="password-drawer"/, 'password change needs a right-side drawer');
assert.match(html, /class="logout-dialog"/, 'logout needs a confirmation dialog');
assert.match(html, /id="current-password"/, 'password form needs current password');
assert.match(html, /id="new-password"/, 'password form needs new password');
assert.match(html, /id="confirm-password"/, 'password form needs confirmation');

assert.match(html, /class="public-header-actions"/, 'public navigation and login must share a right-aligned action group');
assert.match(iterationCss, /\.public-header-actions[^}]*margin-left:\s*auto/s, 'public header actions must align right');
assert.ok((html.match(/data-admin-tab=/g) || []).length >= 5, 'management center needs five primary sections');
assert.ok((html.match(/class="admin-metric/g) || []).length >= 4, 'management overview needs operational metrics');
assert.match(html, /class="admin-user-ledger"/, 'management center needs a user ledger');
assert.match(html, /class="admin-role-grid"/, 'management center needs role and permission cards');
assert.match(html, /class="admin-audit-ledger"/, 'management center needs audit records');
assert.match(html, /class="admin-settings"/, 'management center needs system settings');
assert.match(js, /adminTab/, 'management section tabs need interactive behavior');
assert.match(html, /class="admin-console-layout"/, 'management center needs a stable local navigation layout');
for (const adminPanel of ['kb-admin', 'document-admin', 'knowledge-traces', 'research-traces']) {
  assert.match(html, new RegExp(`data-admin-panel=["']${adminPanel}["']`), `missing ${adminPanel} management panel`);
  assert.match(html, new RegExp(`data-admin-tab=["']${adminPanel}["']`), `missing ${adminPanel} management destination`);
}
assert.match(html, /class="admin-kb-ledger"/, 'management center needs an organization-wide knowledge base ledger');
assert.match(html, /class="admin-document-ledger"/, 'management center needs an organization-wide document ledger');
assert.match(html, /class="pipeline-trace-ledger knowledge"/, 'management center needs Knowledge Pipeline traces');
assert.match(html, /class="pipeline-trace-ledger research"/, 'management center needs Research Pipeline traces');
assert.match(html, /class="pipeline-trace-drawer"/, 'pipeline traces need an inspectable detail surface');
assert.match(html, /per-KB Collection/, 'document ingestion trace must expose per-KB collection publication');
for (const action of ['open-pipeline-trace', 'close-pipeline-trace']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']`), `missing ${action} trace control`);
  assert.match(js, new RegExp(`['"]${action}['"]`), `missing ${action} trace behavior`);
}
assert.match(html, /data-admin-tab="billing"/, 'management navigation needs a dedicated cost and billing destination');
assert.match(html, /data-admin-panel="billing"/, 'management center needs a dedicated cost and billing panel');
assert.match(html, /class="billing-usage-ledger"/, 'cost and billing needs token and cost usage records');
assert.doesNotMatch(html, /class="trace-json-details"/, 'pipeline trace must not keep a detached full-trace JSON block');
assert.doesNotMatch(html, /id="pipeline-trace-json"/, 'pipeline trace must not keep a detached full-trace JSON output');
assert.match(js, /phaseJson/, 'pipeline trace behavior needs phase-level JSON payloads');
assert.match(js, /phase-json-details/, 'pipeline trace behavior needs expandable JSON within each phase');
const knowledgeTracePanel = html.match(/data-admin-panel="knowledge-traces"[\s\S]*?(?=<div class="admin-panel" data-admin-panel="research-traces")/)?.[0] || '';
const researchTracePanel = html.match(/data-admin-panel="research-traces"[\s\S]*?(?=<div class="admin-panel" data-admin-panel="billing")/)?.[0] || '';
assert.doesNotMatch(knowledgeTracePanel, /tokens|¥/, 'Knowledge Pipeline list must not mix in token or cost accounting');
assert.doesNotMatch(researchTracePanel, /tokens|¥/, 'Research Pipeline list must not mix in token or cost accounting');
assert.match(html, /耗时 \/ 重试/, 'pipeline trace ledgers must prioritize timing and retry diagnostics');
const pipelineTraceDrawerMarkup = html.match(/class="pipeline-trace-drawer"[\s\S]*?<\/aside>/)?.[0] || '';
assert.doesNotMatch(pipelineTraceDrawerMarkup, /tokens|¥|成本/, 'pipeline trace detail must not duplicate usage or cost accounting');
assert.match(html, /class="[^"]*admin-primary-sidebar[^"]*"/, 'management center needs its own first-level sidebar');
assert.match(html, /href="#workbench"[^>]*class="admin-return"/, 'management sidebar needs a direct return to workbench');
assert.match(js, /classList\.toggle\(['"]admin-mode['"]/, 'admin route must switch the app into an independent shell');
assert.match(iterationCss, /\.app-shell\.admin-mode \.app-sidebar[^}]*display:\s*none/s, 'independent admin shell must hide the workbench sidebar');

console.log('knowledge prototype structure: passed');
