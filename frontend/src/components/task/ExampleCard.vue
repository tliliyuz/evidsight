<template>
  <div class="example-card" @click="$emit('select', example)">
    <p class="example-topic">{{ truncatedTopic }}</p>
    <span class="example-type-tag">{{ typeLabel }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 示例对象：{ topic, task_type, label } */
  example: {
    type: Object,
    required: true,
  },
})

defineEmits(['select'])

// —— 主题截断（50 字符） ——
const truncatedTopic = computed(() => {
  const t = props.example.topic || ''
  return t.length > 50 ? t.slice(0, 50) + '...' : t
})

// —— 类型中文标签 ——
const TYPE_LABELS = {
  comparison: '对比',
  explainer: '解释',
  analysis: '影响',
}

const typeLabel = computed(() => {
  return TYPE_LABELS[props.example.task_type] || props.example.task_type
})
</script>

<style scoped>
.example-card {
  border: 1px solid var(--rm-border);
  border-radius: var(--rm-radius-lg);
  padding: var(--rm-space-3_5);
  cursor: pointer;
  transition: all var(--rm-transition-fast);
  text-align: left;
}

.example-card:hover {
  border-color: rgba(15, 118, 110, 0.3);
  background: rgba(15, 118, 110, 0.05);
}

.example-topic {
  font-size: var(--rm-text-xs);
  color: var(--rm-text-primary);
  margin: 0 0 var(--rm-space-1_5) 0;
  line-height: var(--rm-leading-body);
}

.example-type-tag {
  font-size: var(--rm-text-3xs);
  color: var(--rm-primary);
  font-weight: var(--rm-weight-semibold);
}
</style>
