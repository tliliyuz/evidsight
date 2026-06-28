<template>
  <div class="evidence-panel">
    <div class="panel-header">
      <button
        v-if="filterSectionId"
        class="clear-filter"
        @click="$emit('filter', null)"
      >
        清除筛选
      </button>
    </div>

    <div ref="listRef" class="evidence-list">
      <div
        v-for="item in sortedEvidence"
        :key="item.index"
        :data-evidence-index="item.index"
        class="evidence-card"
        :class="{ flash: highlightedIndex === item.index }"
        @click="$emit('select', item.index)"
      >
        <div class="evidence-header">
          <span class="evidence-tag">来源{{ item.index + 1 }}</span>
          <span v-if="item.relevanceScore != null" class="evidence-score">
            {{ (item.relevanceScore * 100).toFixed(0) }}%
          </span>
        </div>

        <a
          v-if="item.sourceUrl"
          class="evidence-source"
          :href="item.sourceUrl"
          target="_blank"
          rel="noopener,noreferrer"
          @click.stop
          :title="item.sourceTitle || item.sourceUrl"
        >
          <i class="fas fa-up-right-from-square"></i>
          <span class="evidence-source-title">{{ item.sourceTitle || item.domain || '来源链接' }}</span>
        </a>

        <p class="evidence-content">{{ item.content }}</p>

        <div class="evidence-meta">
          <div class="evidence-sections">
            <span
              v-for="sectionId in item.usedInSections"
              :key="sectionId"
              class="evidence-section-badge"
              :class="{ active: filterSectionId === sectionId }"
              @click.stop="$emit('filter', sectionId)"
            >
              章节 {{ Number(sectionId) + 1 }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="evidence.length === 0" class="evidence-empty">
        暂无来源
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  evidence: { type: Array, default: () => [] },
  highlightedIndex: { type: Number, default: null },
  filterSectionId: { type: String, default: null },
})

const emit = defineEmits(['select', 'filter'])

const listRef = ref(null)

const sortedEvidence = computed(() => {
  return [...props.evidence].sort((a, b) => a.index - b.index)
})

watch(() => props.highlightedIndex, (index) => {
  if (index == null || !listRef.value) return
  nextTick(() => {
    const card = listRef.value.querySelector(`[data-evidence-index="${index}"]`)
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
})
</script>

<style scoped>
.evidence-panel {
  width: 100%;
  background: var(--rm-bg-page);
  border-left: 1px solid var(--rm-border);
  overflow-y: auto;
  padding: var(--rm-space-3);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--rm-space-2);
}

.panel-title {
  font-size: var(--rm-text-xs);
  font-weight: var(--rm-weight-bold);
  color: var(--rm-text-primary);
}

.clear-filter {
  font-size: var(--rm-text-3xs);
  color: var(--rm-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}

.clear-filter:hover {
  text-decoration: underline;
}

.evidence-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  margin: 0 calc(-1 * var(--rm-space-3));
  padding: 0 var(--rm-space-3);
}

.evidence-card {
  background: var(--rm-bg-card);
  border: 1px solid var(--rm-border);
  border-radius: var(--rm-radius-md);
  padding: var(--rm-space-2);
  font-size: var(--rm-text-2xs);
  transition: all var(--rm-transition-slow);
  position: relative;
  margin-bottom: var(--rm-space-2);
  cursor: pointer;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.evidence-card:hover {
  border-color: var(--rm-primary-border);
  box-shadow: var(--rm-shadow-sm);
}

.evidence-card.flash {
  border-color: var(--rm-evidence-flash-border);
  background: var(--rm-evidence-flash-bg);
  box-shadow: var(--rm-evidence-flash-shadow);
  animation: evidence-flash 1s ease-in-out 2;
}

@keyframes evidence-flash {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.02); }
}

.evidence-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--rm-space-2);
}

.evidence-tag {
  background: var(--rm-primary-hover);
  color: white;
  font-family: var(--rm-font-mono);
  font-size: var(--rm-text-3xs);
  padding: var(--rm-space-0_5) var(--rm-space-1_5);
  border-radius: var(--rm-radius-xs);
  font-weight: var(--rm-weight-bold);
}

.evidence-score {
  font-size: var(--rm-text-3xs);
  color: var(--rm-warning);
  font-weight: var(--rm-weight-bold);
}

.evidence-source {
  display: inline-flex;
  align-items: center;
  gap: var(--rm-space-1);
  max-width: 100%;
  margin-bottom: var(--rm-space-1);
  color: var(--rm-primary);
  text-decoration: none;
  font-size: var(--rm-text-2xs);
}

.evidence-source:hover {
  text-decoration: underline;
}

.evidence-source i {
  font-size: var(--rm-text-3xs);
  flex-shrink: 0;
}

.evidence-source-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-content {
  color: var(--rm-text-secondary);
  line-height: var(--rm-leading-body);
  margin: 0 0 var(--rm-space-1_5) 0;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: break-word;
  word-break: break-word;
}

.evidence-meta {
  font-size: var(--rm-text-3xs);
  color: var(--rm-text-tertiary);
  border-top: 1px solid var(--rm-border-light);
  padding-top: var(--rm-space-1);
  display: flex;
  justify-content: space-between;
}

.evidence-sections {
  display: flex;
  flex-wrap: wrap;
  gap: var(--rm-space-1);
}

.evidence-section-badge {
  background: var(--rm-bg-elevated);
  color: var(--rm-text-tertiary);
  padding: var(--rm-space-0_5) var(--rm-space-1_5);
  border-radius: var(--rm-radius-pill);
  cursor: pointer;
  transition: all var(--rm-transition-fast);
}

.evidence-section-badge:hover,
.evidence-section-badge.active {
  background: var(--rm-primary-light);
  color: var(--rm-primary);
}

.evidence-empty {
  color: var(--rm-text-tertiary);
  text-align: center;
  padding: var(--rm-space-6) 0;
  font-size: var(--rm-text-xs);
}
</style>
