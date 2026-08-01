/**
 * ReportStore 单元测试 — 覆盖 src/stores/report.js
 *
 * - fetch() 规范化 sections/evidence/trace
 * - selectSection / highlightEvidence / setEvidenceFilter 状态变化
 * - clear() 重置全部状态
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useReportStore } from '@/stores/report'
import * as researchApi from '@/api/research'

vi.mock('@/api/research', () => ({
  getReport: vi.fn(),
}))

function mockReportResponse() {
  return {
    data: {
      data: {
        task_id: 'task-report-1',
        status: 'completed',
        report: {
          title: '量子计算对密码学的影响',
          generated_at: '2026-06-24T10:00:00Z',
          sections: [
            {
              heading: '1. 量子计算威胁概述',
              content: '量子计算机可破解 RSA [来源0]。',
              sources: [{ id: 1, evidence_index: 0 }],
            },
            {
              heading: '2. PQC 应对方案',
              content: 'NIST 已发布 PQC 标准 [来源0][来源1]。',
              sources: [{ id: 1, evidence_index: 0 }, { id: 2, evidence_index: 1 }],
            },
          ],
          sources: [
            { id: 1, url: 'https://nist.gov/pqc', title: 'NIST PQC', domain: 'nist.gov' },
            { id: 2, url: 'https://example.com/shor', title: "Shor's Algorithm", domain: 'example.com' },
          ],
        },
        evidence_graph: {
          items: [
            { index: 0, source_id: 1, content: 'RSA vulnerable...', relevance_score: 0.92, used_in_sections: ['0', '1'] },
            { index: 1, source_id: 2, content: "Shor's algorithm...", relevance_score: 0.88, used_in_sections: ['1'] },
          ],
        },
        trace: {
          phases: {
            planning: { duration_ms: 1200 },
            search: { total_results: 45, selected: 10, duration_ms: 3500 },
          },
          phase_durations_ms: {
            planning: 1200,
            search: 3500,
          },
          total_duration_ms: 4700,
        },
      },
    },
  }
}

describe('ReportStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('fetch', () => {
    it('fetch 成功_规范化 sections', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')

      expect(researchApi.getReport).toHaveBeenCalledWith('task-report-1')
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.sections).toHaveLength(2)
      expect(store.sections[0].id).toBe('0')
      expect(store.sections[0].heading).toBe('1. 量子计算威胁概述')
      expect(store.sections[0].sources).toEqual([{ id: 1, evidenceIndex: '0' }])
    })

    it('fetch 成功_按 index 排序 evidence', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')

      expect(store.evidence).toHaveLength(2)
      expect(store.evidence[0].index).toBe(0)
      expect(store.evidence[1].index).toBe(1)
      expect(store.evidence[0].usedInSections).toEqual(['0', '1'])
      expect(store.evidence[1].usedInSections).toEqual(['1'])
    })

    it('fetch 成功_默认选中第一章节', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')

      expect(store.selectedSectionId).toBe('0')
    })

    it('fetch 成功_将嵌套 trace 扁平化', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')

      expect(store.trace).not.toBeNull()
      expect(store.trace.planning.duration_ms).toBe(1200)
      expect(store.trace.search.selected).toBe(10)
      expect(store.trace.search.total_results).toBe(45)
      // 未返回的阶段仍生成对象，duration_ms 为 null
      expect(store.trace.render).toBeDefined()
    })

    it('fetch 成功_evidence 携带来源信息', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')

      expect(store.evidence[0].sourceUrl).toBe('https://nist.gov/pqc')
      expect(store.evidence[0].sourceTitle).toBe('NIST PQC')
      expect(store.evidence[0].domain).toBe('nist.gov')
      expect(store.evidence[1].sourceUrl).toBe('https://example.com/shor')
    })

    it('fetch 失败_设置 error 并清空数据', async () => {
      researchApi.getReport.mockRejectedValue(new Error('网络错误'))

      const store = useReportStore()
      store.sections = [{ id: '0', heading: '旧数据' }]
      await store.fetch('task-report-1')

      expect(store.loading).toBe(false)
      expect(store.error).toBeDefined()
      expect(store.sections).toEqual([])
      expect(store.evidence).toEqual([])
    })
  })

  describe('selectSection', () => {
    it('selectSection 更新 selectedSectionId', () => {
      const store = useReportStore()
      store.sections = [{ id: '0', heading: 'A' }, { id: '1', heading: 'B' }]
      store.selectSection('1')
      expect(store.selectedSectionId).toBe('1')
    })
  })

  describe('highlightEvidence', () => {
    it('highlightEvidence 更新高亮索引', () => {
      const store = useReportStore()
      store.highlightEvidence(3)
      expect(store.highlightedEvidenceIndex).toBe(3)
    })

    it('highlightEvidence 可清除高亮', () => {
      const store = useReportStore()
      store.highlightEvidence(3)
      store.highlightEvidence(null)
      expect(store.highlightedEvidenceIndex).toBeNull()
    })
  })

  describe('setEvidenceFilter', () => {
    it('setEvidenceFilter 按章节筛选 evidence', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')
      store.setEvidenceFilter('1')

      expect(store.evidenceFilterSectionId).toBe('1')
      expect(store.filteredEvidence).toHaveLength(2)
      expect(store.filteredEvidence.map(e => e.index)).toEqual([0, 1])
    })

    it('setEvidenceFilter null 显示全部 evidence', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')
      store.setEvidenceFilter('1')
      store.setEvidenceFilter(null)

      expect(store.filteredEvidence).toHaveLength(2)
    })
  })

  describe('clear', () => {
    it('clear 重置所有状态', async () => {
      researchApi.getReport.mockResolvedValue(mockReportResponse())

      const store = useReportStore()
      await store.fetch('task-report-1')
      store.selectSection('1')
      store.highlightEvidence(0)
      store.setEvidenceFilter('1')

      store.clear()

      expect(store.report).toBeNull()
      expect(store.sections).toEqual([])
      expect(store.evidence).toEqual([])
      expect(store.trace).toBeNull()
      expect(store.selectedSectionId).toBeNull()
      expect(store.highlightedEvidenceIndex).toBeNull()
      expect(store.evidenceFilterSectionId).toBeNull()
    })
  })
})
