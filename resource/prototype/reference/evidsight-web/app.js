(() => {
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  const landing = document.querySelector('#landing');
  const app = document.querySelector('#app');
  const drawer = document.querySelector('#login-drawer');
  const backdrop = document.querySelector('#login-backdrop');
  const loginForm = document.querySelector('#login-form');
  const password = document.querySelector('#password');
  const routeTitle = document.querySelector('#route-title');
  const placeholderTitle = document.querySelector('#placeholder-title');
  const evidencePanel = document.querySelector('#evidence-panel');
  const reportLayout = document.querySelector('#report-layout');
  const evidenceNumber = document.querySelector('#evidence-number');
  const uploadDrawer = document.querySelector('#upload-drawer');
  const uploadBackdrop = document.querySelector('#upload-backdrop');
  const chatShell = document.querySelector('.chat-shell');
  const chatSourcePanel = document.querySelector('#chat-source-panel');
  const chatSourceNumber = document.querySelector('#chat-source-number');
  const chatForm = document.querySelector('#chat-form');
  const chatInput = document.querySelector('#chat-input');
  const messageStream = document.querySelector('#message-stream');
  const kbScopePopover = document.querySelector('#kb-scope-popover');
  const chunkDrawer = document.querySelector('#chunk-drawer');
  const chunkBackdrop = document.querySelector('#chunk-backdrop');
  const researchCreateForm = document.querySelector('#research-create-form');
  const accountButton = document.querySelector('[data-action="toggle-account-menu"]');
  const accountMenu = document.querySelector('#account-menu');
  const passwordDrawer = document.querySelector('#password-drawer');
  const passwordBackdrop = document.querySelector('#password-backdrop');
  const passwordForm = document.querySelector('#password-form');
  const passwordFormError = document.querySelector('#password-form-error');
  const passwordStrength = document.querySelector('.password-strength');
  const logoutDialog = document.querySelector('#logout-dialog');
  const logoutBackdrop = document.querySelector('#logout-backdrop');
  const pipelineTraceDrawer = document.querySelector('#pipeline-trace-drawer');
  const pipelineTraceBackdrop = document.querySelector('#pipeline-trace-backdrop');
  const focusableSelector = 'button, a[href], input, textarea, [tabindex]:not([tabindex="-1"])';
  let lastFocused = null;

  const routes = {
    workbench: { view: 'workbench', title: '工作台' },
    research: { view: 'research', title: '研究现场' },
    'research-create': { view: 'research-create', title: '深度研究' },
    'research-tasks': { view: 'research-tasks', title: '研究任务' },
    report: { view: 'report', title: '研究报告' },
    chat: { view: 'chat', title: '据见问答' },
    'chat-history': { view: 'chat-history', title: '问答历史' },
    knowledge: { view: 'knowledge', title: '知识库' },
    'knowledge-detail': { view: 'knowledge-detail', title: '知识库详情' },
    admin: { view: 'admin', title: '管理中心' }
  };

  function openLogin() {
    lastFocused = document.activeElement;
    backdrop.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      backdrop.classList.add('open');
      drawer.classList.add('open');
      drawer.querySelector('input').focus();
    });
    document.body.style.overflow = 'hidden';
  }

  function closeLogin() {
    backdrop.classList.remove('open');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    window.setTimeout(() => { backdrop.hidden = true; }, 320);
    lastFocused?.focus();
  }

  function showApp(routeName) {
    const route = routes[routeName] || routes.workbench;
    landing.hidden = true;
    app.hidden = false;
    app.classList.toggle('admin-mode', route.view === 'admin');
    document.querySelectorAll('[data-route-view]').forEach(view => {
      view.hidden = view.dataset.routeView !== route.view;
    });
    document.querySelectorAll('[data-route]').forEach(link => {
      link.classList.toggle('active', link.dataset.route === routeName);
    });
    routeTitle.textContent = route.title;
    if (route.view === 'placeholder') placeholderTitle.textContent = route.title;
    closeEvidence();
    window.scrollTo({ top: 0, behavior: 'auto' });
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' })));
  }

  function route() {
    const hash = location.hash.slice(1) || 'landing';
    if (hash === 'landing' || ['narrative', 'research-method', 'evidence-story'].includes(hash)) {
      app.classList.remove('admin-mode');
      app.hidden = true;
      landing.hidden = false;
      if (hash === 'landing') requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
      return;
    }
    showApp(hash);
  }

  function openEvidence(number) {
    evidenceNumber.textContent = number;
    evidencePanel.setAttribute('aria-hidden', 'false');
    document.querySelectorAll('.citation-button').forEach(button => {
      button.classList.toggle('active', button.dataset.evidence === number);
    });
    document.querySelectorAll('[data-evidence-node]').forEach(node => {
      node.classList.toggle('active', node.dataset.evidenceNode === number);
    });
    const evidenceNode = document.querySelector(`[data-evidence-node="${number}"]`);
    evidenceNode?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const citedSection = document.querySelector(`.citation-button[data-evidence="${number}"]`)?.closest('section')?.id;
    if (citedSection) setActiveReportSection(citedSection);
  }

  function closeEvidence() {
    evidencePanel?.setAttribute('aria-hidden', 'false');
    document.querySelectorAll('.citation-button').forEach(button => button.classList.remove('active'));
  }

  function locateCitationFromEvidence(number) {
    openEvidence(number);
    document.querySelector(`.citation-button[data-evidence="${number}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function setActiveReportSection(sectionId) {
    document.querySelectorAll('[data-report-section]').forEach(link => {
      link.classList.toggle('active', link.dataset.reportSection === sectionId);
    });
  }

  function openUpload() {
    uploadBackdrop.hidden = false;
    uploadDrawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      uploadBackdrop.classList.add('open');
      uploadDrawer.classList.add('open');
      uploadDrawer.querySelector('[data-action="close-upload"]').focus();
    });
  }

  function closeUpload() {
    uploadBackdrop.classList.remove('open');
    uploadDrawer.classList.remove('open');
    uploadDrawer.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { uploadBackdrop.hidden = true; }, 320);
  }

  function openChatSource(number) {
    chatSourceNumber.textContent = number;
    chatShell.classList.add('source-open');
    chatSourcePanel.setAttribute('aria-hidden', 'false');
  }

  function closeChatSource() {
    chatShell?.classList.remove('source-open');
    chatSourcePanel?.setAttribute('aria-hidden', 'true');
  }

  function toggleOverlay(element, open) {
    if (!element) return;
    element.classList.toggle('open', open);
    element.setAttribute('aria-hidden', String(!open));
  }

  function openChunks(documentName) {
    document.querySelector('#chunk-title').textContent = documentName || '2026_H2_Product_Roadmap.pdf';
    chunkBackdrop.hidden = false;
    chunkDrawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      chunkBackdrop.classList.add('open');
      chunkDrawer.classList.add('open');
    });
  }

  function closeChunks() {
    chunkBackdrop.classList.remove('open');
    chunkDrawer.classList.remove('open');
    chunkDrawer.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { chunkBackdrop.hidden = true; }, 280);
  }

  function filterRows(selector, predicate) {
    document.querySelectorAll(selector).forEach(row => { row.hidden = !predicate(row); });
  }

  function setAdminTab(adminTab) {
    document.querySelectorAll('.admin-tabs [data-admin-tab]').forEach(button => {
      button.classList.toggle('active', button.dataset.adminTab === adminTab);
    });
    document.querySelectorAll('[data-admin-panel]').forEach(panel => {
      const active = panel.dataset.adminPanel === adminTab;
      panel.hidden = !active;
      panel.classList.toggle('active', active);
    });
    document.querySelector('.admin-route')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function openPipelineTrace(kind = 'knowledge') {
    const traceConfig = {
      knowledge: { label: 'KNOWLEDGE PIPELINE TRACE', title: 'ktr_7A91F2', request: 'REQUEST · req_21CE', status: 'SUCCESS', duration: '3.82s', retries: '1 / 0', steps: 'knowledge-trace-steps', phaseJson: [
        { phase: 'intent_classification', trace_id: 'ktr_7A91F2', duration_ms: 84, attempt: 1, result: { intent: 'research_compare', confidence: 0.94 }, version: 'intent-v4', safe_error_code: null },
        { phase: 'query_rewrite', trace_id: 'ktr_7A91F2', duration_ms: 312, attempt: 1, counts: { input_queries: 1, output_queries: 3 }, version: 'rewrite-v5', safe_error_code: null },
        { phase: 'authorization', trace_id: 'ktr_7A91F2', duration_ms: 96, attempt: 1, counts: { requested_kb: 2, authorized_kb: 2 }, policy: 'request_time_recheck', safe_error_code: null },
        { phase: 'hybrid_retrieval', trace_id: 'ktr_7A91F2', duration_ms: 1240, attempt: 1, counts: { vector_candidates: 62, bm25_candidates: 48 }, version: 'retrieval-v7', degraded: false },
        { phase: 'fusion_rerank', trace_id: 'ktr_7A91F2', duration_ms: 718, attempt: 2, counts: { fused: 96, reranked: 34 }, version: 'reranker-v3', safe_error_code: 'PROVIDER_TIMEOUT' },
        { phase: 'evidence_review', trace_id: 'ktr_7A91F2', duration_ms: 310, attempt: 1, counts: { reviewed: 34, accepted: 8 }, completeness: 0.92, version: 'evidence-gate-v2' },
        { phase: 'generation', trace_id: 'ktr_7A91F2', duration_ms: 1060, attempt: 1, provider: 'model_gateway', status: 'completed', safe_error_code: null }
      ] },
      research: { label: 'RESEARCH PIPELINE TRACE', title: 'EV-20260731-042', request: 'TRACE · rtr_A829D0 · REQUEST · req_21B4', status: 'RUNNING', duration: '08:43', retries: '1 / 0', steps: 'research-trace-steps', phaseJson: [
        { phase: 'planning', trace_id: 'rtr_A829D0', task_id: 'EV-20260731-042', duration_ms: 128000, attempt: 1, counts: { dimensions: 4 }, version: 'research-plan-v2' },
        { phase: 'searching', trace_id: 'rtr_A829D0', duration_ms: 196000, attempt: 1, counts: { web_candidates: 48, internal_kb: 2 }, linked_traces: ['ktr_7A90D8'] },
        { phase: 'fetching', trace_id: 'rtr_A829D0', duration_ms: 94000, attempt: 1, counts: { succeeded: 43, degraded: 1 }, safe_error_codes: ['SOURCE_UNAVAILABLE'] },
        { phase: 'reranking', trace_id: 'rtr_A829D0', duration_ms: 68000, attempt: 2, counts: { candidates: 96, evidence: 34 }, version: 'reranker-v3' },
        { phase: 'synthesizing', trace_id: 'rtr_A829D0', elapsed_ms: 134000, attempt: 1, status: 'running', steps: { completed: 18, total: 27 }, recoverable: true },
        { phase: 'evidence_graph', trace_id: 'rtr_A829D0', status: 'pending', attempt: 0, blocked_by: 'synthesizing' },
        { phase: 'rendering', trace_id: 'rtr_A829D0', status: 'pending', attempt: 0, blocked_by: 'evidence_graph' }
      ] },
      ingestion: { label: 'DOCUMENT INGESTION TRACE', title: 'doc_8f21', request: 'TRACE · itr_82C7 · KB · kb_91ad', status: 'COMPLETED', duration: '01:48', retries: '0 / 0', steps: 'ingestion-trace-steps', phaseJson: [
        { phase: 'upload_validate', trace_id: 'itr_82C7', duration_ms: 142, attempt: 1, checksum_verified: true, safe_error_code: null },
        { phase: 'parse_document', trace_id: 'itr_82C7', duration_ms: 18400, attempt: 1, parser: 'pdf-v4', counts: { pages: 18 } },
        { phase: 'chunk', trace_id: 'itr_82C7', duration_ms: 12600, attempt: 1, policy: 'chunk-v7', counts: { chunks: 1284 } },
        { phase: 'embedding', trace_id: 'itr_82C7', duration_ms: 48200, attempt: 1, model: 'embedding-v3', counts: { batches: 38 } },
        { phase: 'write_staging_index', trace_id: 'itr_82C7', duration_ms: 21600, attempt: 1, collection: 'kb_91ad_staging_v42' },
        { phase: 'publish_collection', trace_id: 'itr_82C7', duration_ms: 7040, attempt: 1, target: 'kb_91ad', previous_version: 41, published_version: 42, atomic_switch: true }
      ] }
    }[kind];
    document.querySelector('#pipeline-trace-kind').textContent = traceConfig.label;
    document.querySelector('#pipeline-trace-title').textContent = traceConfig.title;
    document.querySelector('#pipeline-trace-request').textContent = traceConfig.request;
    document.querySelector('#pipeline-trace-status').textContent = traceConfig.status;
    document.querySelector('#pipeline-trace-duration').textContent = traceConfig.duration;
    document.querySelector('#pipeline-trace-retries').textContent = traceConfig.retries;
    document.querySelectorAll('.trace-step-list').forEach(list => { list.hidden = list.id !== traceConfig.steps; });
    const activePhaseList = document.querySelector(`#${traceConfig.steps}`);
    activePhaseList.querySelectorAll('.phase-json-details').forEach(details => details.remove());
    [...activePhaseList.children].forEach((phaseRow, index) => {
      const details = document.createElement('details');
      details.className = 'phase-json-details';
      const summary = document.createElement('summary');
      summary.innerHTML = '<span>查看此 Phase JSON</span><i>STRUCTURED · SAFE</i>';
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(traceConfig.phaseJson[index], null, 2);
      details.append(summary, pre);
      phaseRow.append(details);
    });
    pipelineTraceBackdrop.hidden = false;
    pipelineTraceDrawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      pipelineTraceBackdrop.classList.add('open');
      pipelineTraceDrawer.classList.add('open');
    });
  }

  function closePipelineTrace() {
    pipelineTraceBackdrop.classList.remove('open');
    pipelineTraceDrawer.classList.remove('open');
    pipelineTraceDrawer.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { pipelineTraceBackdrop.hidden = true; }, 280);
  }

  function closeAccountMenu() {
    accountMenu.classList.remove('open');
    accountMenu.setAttribute('aria-hidden', 'true');
    accountButton.setAttribute('aria-expanded', 'false');
  }

  function toggleAccountMenu() {
    const open = !accountMenu.classList.contains('open');
    accountMenu.classList.toggle('open', open);
    accountMenu.setAttribute('aria-hidden', String(!open));
    accountButton.setAttribute('aria-expanded', String(open));
  }

  function openPassword() {
    closeAccountMenu();
    passwordBackdrop.hidden = false;
    passwordDrawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      passwordBackdrop.classList.add('open');
      passwordDrawer.classList.add('open');
      document.querySelector('#current-password').focus();
    });
  }

  function closePassword() {
    passwordBackdrop.classList.remove('open');
    passwordDrawer.classList.remove('open');
    passwordDrawer.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { passwordBackdrop.hidden = true; }, 300);
  }

  function openLogout() {
    closeAccountMenu();
    logoutBackdrop.hidden = false;
    logoutDialog.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      logoutBackdrop.classList.add('open');
      logoutDialog.classList.add('open');
      logoutDialog.querySelector('[data-action="close-logout"]').focus();
    });
  }

  function closeLogout() {
    logoutBackdrop.classList.remove('open');
    logoutDialog.classList.remove('open');
    logoutDialog.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { logoutBackdrop.hidden = true; }, 260);
  }

  function confirmLogout() {
    closeLogout();
    closeAccountMenu();
    location.hash = 'landing';
    window.setTimeout(openLogin, 280);
  }

  // ===== 主题切换 =====
  const THEME_KEY = 'evidsight-theme';
  const themeDialog = document.querySelector('#theme-dialog');
  const themeBackdrop = document.querySelector('#theme-backdrop');
  const themeConfirm = document.querySelector('#theme-confirm');
  const themeConfirmBackdrop = document.querySelector('#theme-confirm-backdrop');
  const themeConfirmText = document.querySelector('#theme-confirm-text');
  const lightThemeLink = document.querySelector('#light-theme');
  let pendingTheme = null;

  function currentTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return lightThemeLink && !lightThemeLink.disabled ? 'light' : 'dark';
  }

  function applyTheme(theme) {
    if (lightThemeLink) lightThemeLink.disabled = theme !== 'light';
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.content = theme;
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem(THEME_KEY, theme);
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
      const selected = button.dataset.themeChoice === theme;
      button.classList.toggle('selected', selected);
      const check = button.querySelector('.theme-check');
      if (check) check.style.visibility = selected ? 'visible' : 'hidden';
    });
    const label = document.getElementById('theme-current-label');
    if (label) label.textContent = `当前：${theme === 'light' ? '浅色' : '深色'}`;
  }

  function openTheme() {
    closeAccountMenu();
    applyTheme(currentTheme());
    themeBackdrop.hidden = false;
    themeDialog.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      themeBackdrop.classList.add('open');
      themeDialog.classList.add('open');
      themeDialog.querySelector('.theme-option')?.focus();
    });
  }

  function closeTheme() {
    themeBackdrop.classList.remove('open');
    themeDialog.classList.remove('open');
    themeDialog.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { themeBackdrop.hidden = true; }, 260);
  }

  function openThemeConfirm(theme) {
    pendingTheme = theme;
    themeConfirmText.textContent = `确定切换到${theme === 'light' ? '浅色' : '深色'}主题吗？切换会立即生效。`;
    themeConfirmBackdrop.hidden = false;
    themeConfirm.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      themeConfirmBackdrop.classList.add('open');
      themeConfirm.classList.add('open');
      themeConfirm.querySelector('[data-action="close-theme-confirm"]').focus();
    });
  }

  function closeThemeConfirm() {
    themeConfirmBackdrop.classList.remove('open');
    themeConfirm.classList.remove('open');
    themeConfirm.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => { themeConfirmBackdrop.hidden = true; }, 260);
    pendingTheme = null;
  }

  function confirmTheme() {
    applyTheme(pendingTheme || 'dark');
    closeThemeConfirm();
    closeTheme();
  }

  document.addEventListener('click', event => {
    const action = event.target.closest('[data-action]')?.dataset.action;
    const nav = event.target.closest('[data-nav]')?.dataset.nav;
    const citation = event.target.closest('[data-evidence]')?.dataset.evidence;
    const evidenceNode = event.target.closest('[data-evidence-node]')?.dataset.evidenceNode;
    const reportSection = event.target.closest('[data-report-section]')?.dataset.reportSection;
    const mode = event.target.closest('[data-mode]')?.dataset.mode;
    const adminTab = event.target.closest('[data-admin-tab]')?.dataset.adminTab;

    if (action === 'open-login') openLogin();
    if (action === 'close-login') closeLogin();
    if (action === 'close-evidence') closeEvidence();
    if (action === 'toggle-evidence-graph') evidencePanel.classList.toggle('collapsed');
    if (action === 'open-upload') openUpload();
    if (action === 'close-upload') closeUpload();
    if (action === 'open-chat-source') openChatSource(event.target.closest('[data-source]')?.dataset.source || '01');
    if (action === 'close-chat-source') closeChatSource();
    if (action === 'open-kb-scope') toggleOverlay(kbScopePopover, true);
    if (action === 'close-kb-scope') toggleOverlay(kbScopePopover, false);
    if (action === 'open-chunks') openChunks(event.target.closest('[data-document]')?.dataset.document);
    if (action === 'close-chunks') closeChunks();
    if (action === 'toggle-adjacent-chunks') {
      const adjacent = document.querySelector('.adjacent-chunks');
      adjacent.hidden = !adjacent.hidden;
      event.target.textContent = adjacent.hidden ? '展开相邻切片' : '收起相邻切片';
    }
    if (action === 'open-create-kb') {
      location.hash = 'knowledge-detail';
      window.setTimeout(openUpload, 120);
    }
    if (action === 'start-upload') {
      const button = event.target.closest('[data-action="start-upload"]');
      button.disabled = true;
      button.querySelector('span').textContent = '已提交，后台处理中';
      window.setTimeout(closeUpload, 900);
    }
    if (action === 'retry-document') {
      const button = event.target.closest('[data-action="retry-document"]');
      const row = button.closest('.document-row');
      row.dataset.docKind = 'processing';
      row.querySelector('.doc-state').className = 'doc-state processing';
      row.querySelector('.doc-state').textContent = '已重新排队';
      row.querySelector('.state-reason').textContent = '重试请求已提交，后台继续处理';
      button.disabled = true;
      button.textContent = '已提交';
    }
    if (action === 'new-conversation') {
      document.querySelector('.chat-header h1').textContent = '新的证据对话';
      location.hash = 'chat';
      chatInput.focus();
    }
    if (action === 'toggle-password') {
      password.type = password.type === 'password' ? 'text' : 'password';
      event.target.textContent = password.type === 'password' ? '显示' : '隐藏';
    }
    if (action === 'toggle-account-menu') toggleAccountMenu();
    if (action === 'open-password') openPassword();
    if (action === 'close-password') closePassword();
    if (action === 'submit-password') { /* handled by the password form submit event */ }
    if (action === 'open-logout') openLogout();
    if (action === 'close-logout') closeLogout();
    if (action === 'confirm-logout') confirmLogout();
    if (action === 'open-theme') openTheme();
    if (action === 'close-theme') closeTheme();
    if (action === 'pick-theme') openThemeConfirm(event.target.closest('[data-theme-choice]')?.dataset.themeChoice || 'dark');
    if (action === 'close-theme-confirm') closeThemeConfirm();
    if (action === 'confirm-theme') confirmTheme();
    if (action === 'open-pipeline-trace') openPipelineTrace(event.target.closest('[data-trace-kind]')?.dataset.traceKind || 'knowledge');
    if (action === 'close-pipeline-trace') closePipelineTrace();
    if (action === 'toggle-trace-stage') {
      const stage = event.target.closest('.trace-stage');
      const open = !stage.classList.contains('open');
      stage.classList.toggle('open', open);
      stage.querySelector('[data-action="toggle-trace-stage"]').setAttribute('aria-expanded', String(open));
    }
    if (action === 'locate-trace-evidence') {
      openEvidence(event.target.closest('[data-trace-evidence]').dataset.traceEvidence);
    }
    if (action === 'locate-trace-section') {
      const sectionId = event.target.closest('[data-trace-section]').dataset.traceSection;
      setActiveReportSection(sectionId);
      document.querySelector(`#${sectionId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (nav) location.hash = nav;
    if (citation) openEvidence(citation);
    if (evidenceNode) locateCitationFromEvidence(evidenceNode);
    if (reportSection) {
      event.preventDefault();
      setActiveReportSection(reportSection);
      document.querySelector(`#${reportSection}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (mode) {
      document.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
      document.querySelector('#research-prompt').placeholder = mode === 'chat' ? '向所选知识库提问…' : '描述你希望深入研究的问题…';
    }
    if (adminTab) setAdminTab(adminTab);

    const kbFilter = event.target.closest('[data-kb-filter]')?.dataset.kbFilter;
    if (kbFilter) {
      document.querySelectorAll('[data-kb-filter]').forEach(button => button.classList.toggle('active', button.dataset.kbFilter === kbFilter));
      filterRows('.archive-row', row => kbFilter === 'all' || row.dataset.kbKind === kbFilter);
    }
    const docFilter = event.target.closest('[data-doc-filter]')?.dataset.docFilter;
    if (docFilter) {
      document.querySelectorAll('[data-doc-filter]').forEach(button => button.classList.toggle('active', button.dataset.docFilter === docFilter));
      filterRows('.document-row', row => docFilter === 'all' || (docFilter === 'active' && ['queued', 'processing'].includes(row.dataset.docKind)) || (docFilter === 'issue' && ['partial', 'failed'].includes(row.dataset.docKind)));
    }
    const researchFilter = event.target.closest('[data-research-filter]')?.dataset.researchFilter;
    if (researchFilter) {
      document.querySelectorAll('[data-research-filter]').forEach(button => button.classList.toggle('active', button.dataset.researchFilter === researchFilter));
      filterRows('.research-task-row', row => researchFilter === 'all' || row.dataset.researchKind === researchFilter);
    }
    const chatKbFilter = event.target.closest('[data-chat-kb-filter]')?.dataset.chatKbFilter;
    if (chatKbFilter) {
      document.querySelectorAll('[data-chat-kb-filter]').forEach(button => button.classList.toggle('active', button.dataset.chatKbFilter === chatKbFilter));
      filterRows('.scope-option[data-chat-kb-kind]', row => chatKbFilter === 'all' || row.dataset.chatKbKind === chatKbFilter);
    }
    const kbSelect = event.target.closest('[data-kb-select]');
    if (kbSelect && event.target.closest('.kb-chip button')) kbSelect.remove();
    if (!event.target.closest('.sidebar-bottom') && accountMenu.classList.contains('open')) closeAccountMenu();
  });

  backdrop.addEventListener('click', closeLogin);
  uploadBackdrop.addEventListener('click', closeUpload);
  chunkBackdrop.addEventListener('click', closeChunks);
  passwordBackdrop.addEventListener('click', closePassword);
  logoutBackdrop.addEventListener('click', closeLogout);
  pipelineTraceBackdrop?.addEventListener('click', closePipelineTrace);

  document.querySelector('#new-password')?.addEventListener('input', event => {
    const length = event.target.value.length;
    passwordStrength.classList.toggle('medium', length >= 8 && length < 12);
    passwordStrength.classList.toggle('strong', length >= 12);
    passwordStrength.querySelector('small').textContent = length >= 12 ? '密码强度：强' : length >= 8 ? '密码强度：可用' : '至少需要 8 位字符';
  });

  passwordForm?.addEventListener('submit', event => {
    event.preventDefault();
    const current = document.querySelector('#current-password').value;
    const next = document.querySelector('#new-password').value;
    const confirmation = document.querySelector('#confirm-password').value;
    let message = '';
    if (!current) message = '请输入当前密码。';
    else if (next.length < 8) message = '新密码至少需要 8 位字符。';
    else if (next !== confirmation) message = '两次输入的新密码不一致。';
    passwordFormError.hidden = !message;
    passwordFormError.textContent = message;
    if (message) return;
    const submit = passwordForm.querySelector('[data-action="submit-password"]');
    submit.disabled = true;
    submit.querySelector('span').textContent = '密码已更新';
    window.setTimeout(() => {
      closePassword();
      passwordForm.reset();
      passwordFormError.hidden = true;
      passwordStrength.className = 'password-strength';
      passwordStrength.querySelector('small').textContent = '密码强度将在输入后显示';
      submit.disabled = false;
      submit.querySelector('span').textContent = '更新密码';
    }, 850);
  });

  document.querySelector('#kb-search')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    filterRows('.archive-row', row => row.dataset.kbName.toLowerCase().includes(query) || row.textContent.toLowerCase().includes(query));
  });

  document.querySelector('#doc-search')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    filterRows('.document-row', row => row.textContent.toLowerCase().includes(query));
  });

  document.querySelector('#research-search')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    filterRows('.research-task-row', row => row.textContent.toLowerCase().includes(query));
  });

  document.querySelector('#conversation-search')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    filterRows('.conversation-row', row => row.textContent.toLowerCase().includes(query));
  });

  document.querySelector('#chat-kb-search')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    filterRows('.scope-option[data-chat-kb-kind]', row => row.textContent.toLowerCase().includes(query));
  });

  chatForm?.addEventListener('submit', event => {
    event.preventDefault();
    const question = chatInput.value.trim();
    if (!question) return;
    const userMessage = document.createElement('article');
    userMessage.className = 'message user-message message-right';
    userMessage.innerHTML = `<span class="message-role">YOU · NOW</span><div class="user-bubble"><p>${question.replace(/[&<>]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[char])}</p></div>`;
    const answer = document.createElement('article');
    answer.className = 'message assistant-message chat-loading';
    answer.innerHTML = '<div class="assistant-sign"><span class="message-role">EVIDSIGHT · RETRIEVING</span></div><p>正在当前选定的知识库内检索来源</p>';
    messageStream.append(userMessage, answer);
    chatInput.value = '';
    messageStream.scrollTop = messageStream.scrollHeight;
    window.setTimeout(() => {
      answer.classList.remove('chat-loading');
      answer.innerHTML = '<div class="assistant-sign"><span class="message-role">EVIDSIGHT · NOW</span></div><p>当前原型已完成知识库选择校验与来源检索模拟。正式实现会通过 Chat SSE 流式返回回答，并允许中止本次生成。</p><div class="answer-foot"><span>使用 2 个知识库 · 权限已复核</span><button>复制回答</button></div>';
      messageStream.scrollTop = messageStream.scrollHeight;
    }, 900);
  });

  researchCreateForm?.addEventListener('submit', event => {
    event.preventDefault();
    const submit = researchCreateForm.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.querySelector('span').textContent = '正在创建任务…';
    window.setTimeout(() => { location.hash = 'research'; }, 650);
  });

  drawer.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeLogin();
    if (event.key !== 'Tab') return;
    const focusables = [...drawer.querySelectorAll(focusableSelector)].filter(element => !element.disabled);
    const first = focusables[0];
    const last = focusables.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && uploadDrawer?.classList.contains('open')) closeUpload();
    if (event.key === 'Escape' && chatShell?.classList.contains('source-open')) closeChatSource();
    if (event.key === 'Escape' && kbScopePopover?.classList.contains('open')) toggleOverlay(kbScopePopover, false);
    if (event.key === 'Escape' && chunkDrawer?.classList.contains('open')) closeChunks();
    if (event.key === 'Escape' && accountMenu?.classList.contains('open')) closeAccountMenu();
    if (event.key === 'Escape' && passwordDrawer?.classList.contains('open')) closePassword();
    if (event.key === 'Escape' && logoutDialog?.classList.contains('open')) closeLogout();
    if (event.key === 'Escape' && themeConfirm?.classList.contains('open')) closeThemeConfirm();
    if (event.key === 'Escape' && themeDialog?.classList.contains('open')) closeTheme();
    if (event.key === 'Escape' && pipelineTraceDrawer?.classList.contains('open')) closePipelineTrace();
  });

  loginForm.addEventListener('submit', event => {
    event.preventDefault();
    const submit = loginForm.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.querySelector('span').textContent = '正在验证…';
    window.setTimeout(() => {
      submit.disabled = false;
      submit.querySelector('span').textContent = '进入据见';
      closeLogin();
      location.hash = 'workbench';
    }, 650);
  });

  window.addEventListener('hashchange', route);
  applyTheme(currentTheme());
  route();
})();
