<template>
  <div class="app-layout">
    <Sidebar />
    <div class="main-area">
      <header class="top-header">
        <h1 class="page-title">{{ pageTitle }}</h1>
      </header>
      <main class="content-scroll">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './Sidebar.vue'

const route = useRoute()

const pageTitle = computed(() => {
  const titles = {
    Research: 'ResearchMind',
    History: '历史任务',
  }
  return titles[route.name] || 'ResearchMind'
})
</script>

<style scoped>
.app-layout {
  width: 100%;
  height: 100vh;
  display: flex;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--rm-bg-page);
  overflow: hidden;
}

.top-header {
  height: var(--rm-header-height);
  background: var(--rm-bg-sidebar);
  border-bottom: 1px solid var(--rm-border-dark);
  display: flex;
  align-items: center;
  padding: 0 var(--rm-space-6);
  z-index: 5;
  flex-shrink: 0;
}

.page-title {
  font-size: var(--rm-text-lg);
  font-weight: var(--rm-weight-bold);
  color: var(--rm-text-inverse);
}

.content-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--rm-space-6) var(--rm-space-7);
}
</style>
