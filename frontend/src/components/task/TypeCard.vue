<template>
  <div
    class="type-card"
    :class="{ selected }"
    @click="$emit('select', type)"
  >
    <!-- 选中勾标 -->
    <i v-if="selected" class="fas fa-circle-check check-icon"></i>

    <!-- 图标 + 标题行 -->
    <div class="type-header">
      <i :class="typeIcon"></i>
      <span class="type-title">{{ typeTitle }}</span>
    </div>

    <!-- 描述 -->
    <p class="type-desc">{{ typeDesc }}</p>

    <!-- 示例 -->
    <p class="type-example">{{ typeExample }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 研究类型标识：comparison | explainer | analysis */
  type: {
    type: String,
    required: true,
    validator: (v) => ['comparison', 'explainer', 'analysis'].includes(v),
  },
  /** 是否选中 */
  selected: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['select'])

// —— 类型元数据映射 ——
const TYPE_META = {
  comparison: {
    icon: 'fas fa-balance-scale',
    title: '对比型研究',
    desc: '结构化对比、多源属性提取、维度对齐',
    example: '"2025年主流向量数据库对比"',
  },
  explainer: {
    icon: 'fas fa-lightbulb',
    title: '解释型研究',
    desc: '观点聚类、弱结构输入、综合性强',
    example: '"Transformer 注意力机制的最新改进方向"',
  },
  analysis: {
    icon: 'fas fa-chart-line',
    title: '影响分析型',
    desc: '因果推理、跨域综合、前瞻推断',
    example: '"量子计算对密码学体系的影响"',
  },
}

const meta = computed(() => TYPE_META[props.type] || TYPE_META.comparison)
const typeIcon = computed(() => meta.value.icon)
const typeTitle = computed(() => meta.value.title)
const typeDesc = computed(() => meta.value.desc)
const typeExample = computed(() => meta.value.example)
</script>

<style scoped>
.type-card {
  border: 1px solid var(--rm-border);
  border-radius: var(--rm-radius-lg);
  padding: var(--rm-space-4);
  cursor: pointer;
  transition: all var(--rm-transition-normal);
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 128px;
}

.type-card:hover {
  border-color: #94A3B8;
}

/* 选中态：teal-600 边框 + teal-50/40 背景 + ring-1 */
.type-card.selected {
  border-color: var(--rm-primary);
  background: rgba(15, 118, 110, 0.08);
  box-shadow: 0 0 0 1px var(--rm-primary);
}

/* 选中勾标 — 右上角 */
.check-icon {
  position: absolute;
  top: var(--rm-space-2);
  right: var(--rm-space-2);
  color: var(--rm-primary);
  font-size: var(--rm-text-base);
}

/* 类型图标 + 标题行 */
.type-header {
  display: flex;
  align-items: center;
  gap: var(--rm-space-2);
  color: var(--rm-primary);
  margin-bottom: var(--rm-space-1_5);
}

.type-header i {
  font-size: var(--rm-text-lg);
}

.type-title {
  font-size: var(--rm-text-sm);
  font-weight: var(--rm-weight-semibold);
}

/* 描述 */
.type-desc {
  font-size: var(--rm-text-xs);
  color: var(--rm-text-secondary);
  line-height: var(--rm-leading-body);
  margin: 0;
}

/* 示例 */
.type-example {
  font-size: var(--rm-text-2xs);
  color: var(--rm-text-tertiary);
  margin: var(--rm-space-2) 0 0 0;
}
</style>
