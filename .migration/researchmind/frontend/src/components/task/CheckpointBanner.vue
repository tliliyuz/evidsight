<template>
  <div class="checkpoint-banner">
    <i class="fas fa-save icon"></i>
    <span class="checkpoint-text">
      已保存进度
      <span v-if="checkpoint.phase" class="checkpoint-phase">
        · {{ phaseLabel(checkpoint.phase) }}
      </span>
      <span v-if="checkpoint.savedAt" class="checkpoint-time">
        · {{ formatTime(checkpoint.savedAt) }}
      </span>
    </span>
  </div>
</template>

<script setup>
import { normalizePhaseKey, PHASE_LABELS } from '@/utils/phase'

const props = defineProps({
  checkpoint: { type: Object, required: true },
})

function phaseLabel(phase) {
  const short = normalizePhaseKey(phase)
  return short ? PHASE_LABELS[short] : phase
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const d = new Date(timestamp)
  if (isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<style scoped>
.checkpoint-banner {
  background: var(--rm-primary-subtle-bg);
  border: 1px solid var(--rm-primary-border);
  border-radius: var(--rm-radius-lg);
  padding: var(--rm-space-3);
  display: flex;
  align-items: center;
  gap: var(--rm-space-2_5);
  font-size: var(--rm-text-xs);
  color: var(--rm-text-teal-300);
  margin: 0 var(--rm-space-4) var(--rm-space-4) var(--rm-space-4);
}

.checkpoint-banner .icon {
  color: var(--rm-text-teal-400);
}

.checkpoint-phase {
  color: var(--rm-text-teal-400);
  font-weight: var(--rm-weight-semibold);
}

.checkpoint-time {
  color: var(--rm-text-inverse-dim);
  font-family: var(--rm-font-mono);
}
</style>
