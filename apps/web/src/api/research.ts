/**
 * Research Task v1 API 客户端（API.md §8）—— 工作台最小消费子集。
 *
 * 纠偏 2（AppShell 与工作台）只消费列表端点：顶部运行任务 Chip 需要真实运行中
 * 任务数量，工作台 RECENT RESEARCH 需要来源类型/状态/进度/继续入口。字段契约以
 * `docs/openapi/evidsight-v1.yaml` 的 ResearchTaskListItem 为唯一权威源，不得
 * 绑定 legacy DTO 或手工推断字段。
 */

import type { AxiosInstance } from 'axios'

import { apiClient } from '@/api/client'

export type ResearchTaskStatus =
  'pending' | 'running' | 'completed' | 'partially_completed' | 'failed' | 'canceled' | 'paused'

export type ResearchSourceStrategy = 'knowledge' | 'web' | 'hybrid'

export type ResearchTaskListItem = {
  task_id: string
  topic: string
  status: ResearchTaskStatus
  task_type: string
  source_strategy: ResearchSourceStrategy
  progress: number
  total_sources: number
  total_evidence: number
  report_id: string | null
  created_at: string
  completed_at: string | null
}

export type ResearchTaskList = {
  total: number
  page: number
  page_size: number
  items: ResearchTaskListItem[]
}

export type ResearchApi = {
  listResearchTasks(params?: {
    page?: number
    page_size?: number
    status?: ResearchTaskStatus
    keyword?: string
  }): Promise<ResearchTaskList>
}

export function createResearchApi(client: AxiosInstance): ResearchApi {
  return {
    async listResearchTasks(
      params: {
        page?: number
        page_size?: number
        status?: ResearchTaskStatus
        keyword?: string
      } = {},
    ): Promise<ResearchTaskList> {
      const { data } = await client.get<ResearchTaskList>('/api/v1/research/tasks', { params })
      return data
    },
  }
}

export const researchApi = createResearchApi(apiClient)
