<template>
  <div class="placeholder-page">
    <div class="placeholder-card">
      <i class="fas fa-chart-bar placeholder-icon"></i>
      <h2>系统统计</h2>
      <p>系统运行数据统计与图表 — Phase 5 实现</p>
    </div>
  </div>
</template>

<style scoped>
.placeholder-page { display: flex; align-items: center; justify-content: center; height: 100%; }
.placeholder-card { text-align: center; padding: var(--rm-space-10); background: var(--rm-bg-card); border: 1px solid var(--rm-border); border-radius: var(--rm-radius-xl); max-width: 480px; }
.placeholder-icon { font-size: 48px; color: var(--rm-primary); margin-bottom: var(--rm-space-4); }
.placeholder-card h2 { font-size: var(--rm-text-xl); font-weight: var(--rm-weight-bold); color: var(--rm-text-primary); margin-bottom: var(--rm-space-2); }
.placeholder-card p { font-size: var(--rm-text-body); color: var(--rm-text-tertiary); }
</style>
