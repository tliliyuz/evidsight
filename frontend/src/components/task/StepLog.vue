<template>
  <div class="terminal-panel">
    <div class="terminal-header">
      <span class="terminal-title">实时执行日志</span>
      <div class="terminal-status">
        <span v-if="isLive" class="live-dot"></span>
        <span>{{ statusText }}</span>
      </div>
    </div>

    <div class="terminal-body">
      <div
        v-for="log in displayLogs"
        :key="log.id"
        class="terminal-log-line"
        :class="`log-${log.level}`"
      >
        <i :class="['log-icon', 'fas', log.icon]"></i>
        <span class="terminal-log-time">{{ formatTime(log.timestamp) }}</span>
        <span class="terminal-log-message">{{ log.message || log.label || log.stepType }}</span>
        <span v-if="log.progressText" class="terminal-log-progress">{{ log.progressText }}</span>
      </div>

      <div v-if="displayLogs.length === 0" class="terminal-empty">
        等待任务开始...
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  logs: { type: Array, default: () => [] },
  sseStatus: { type: String, default: 'disconnected' },
})

const isLive = computed(() => props.sseStatus === 'connected' || props.sseStatus === 'reconnecting')

const statusText = computed(() => {
  const map = {
    disconnected: '未连接',
    connecting: '连接中...',
    connected: 'LIVE',
    reconnecting: '重连中...',
    error: '连接失败',
  }
  return map[props.sseStatus] || props.sseStatus
})

const displayLogs = computed(() => {
  return props.logs.map(log => {
    let progressText = ''
    if (log.type === 'step' && log.progress) {
      const p = log.progress
      if (p.label) progressText = `— ${p.label}`
      else if (p.results_found != null) progressText = `— ${p.results_found} 条结果`
      else if (p.progress != null) progressText = `— ${Math.round(p.progress * 100)}%`
    }
    return { ...log, progressText }
  })
})

function formatTime(timestamp) {
  if (!timestamp) return '--:--:--'
  const d = new Date(timestamp)
  if (isNaN(d.getTime())) return '--:--:--'
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<style scoped>
.terminal-panel {
  background: var(--rm-bg-dark-card);
  border: 1px solid var(--rm-border-dark);
  border-radius: var(--rm-radius-xl);
  display: flex;
  flex-direction: column;
  box-shadow: var(--rm-shadow-2xl);
  margin: 0 var(--rm-space-4) var(--rm-space-4) var(--rm-space-4);
  flex: 1;
  min-height: 240px;
  overflow: hidden;
}

.terminal-header {
  background: var(--rm-bg-terminal-header);
  padding: var(--rm-space-2) var(--rm-space-4);
  border-bottom: 1px solid var(--rm-border-dark);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.terminal-title {
  font-family: var(--rm-font-mono);
  font-size: var(--rm-text-xs);
  color: var(--rm-text-inverse-secondary);
}

.terminal-status {
  display: flex;
  align-items: center;
  gap: var(--rm-space-1_5);
  font-size: var(--rm-text-3xs);
  font-family: var(--rm-font-mono);
  color: var(--rm-text-inverse-dim);
}

.terminal-status .live-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--rm-radius-full);
  background: var(--rm-success);
  animation: ping 1s cubic-bezier(0, 0, 0.2, 1) infinite;
}

@keyframes ping {
  75%, 100% { transform: scale(2); opacity: 0; }
}

.terminal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--rm-space-4);
  font-family: var(--rm-font-mono);
  font-size: var(--rm-text-xs);
  color: var(--rm-text-inverse-secondary);
  background: var(--rm-bg-dark-card);
}

.terminal-empty {
  color: var(--rm-text-inverse-dim);
  text-align: center;
  padding: var(--rm-space-8) 0;
}

.terminal-log-line {
  display: flex;
  align-items: flex-start;
  gap: var(--rm-space-2);
  line-height: 1.625;
  margin-bottom: var(--rm-space-2);
}

.log-icon {
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.terminal-log-time {
  color: var(--rm-text-inverse-dim);
  flex-shrink: 0;
  user-select: none;
}

.terminal-log-message {
  word-break: break-word;
}

.terminal-log-progress {
  color: var(--rm-text-inverse-dim);
  margin-left: var(--rm-space-1);
}

.log-info { color: var(--rm-text-inverse-secondary); }
.log-info .log-icon { color: var(--rm-text-inverse-dim); }

.log-success { color: var(--rm-text-slate-300); }
.log-success .log-icon { color: var(--rm-status-success-light); }

.log-warning { color: var(--rm-text-amber-400); font-weight: var(--rm-weight-bold); }
.log-warning .log-icon { color: var(--rm-warning); }

.log-error { color: var(--rm-text-rose-400); font-weight: var(--rm-weight-bold); }
.log-error .log-icon { color: var(--rm-danger); }

.log-muted { color: var(--rm-text-inverse-dim); }
.log-muted .log-icon { color: var(--rm-text-inverse-dim); }

</style>
