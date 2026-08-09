import type { AxiosAdapter, AxiosInstance } from 'axios'

import { apiClient, createApiClient } from '@/api/client'

/** 知识库可见范围（对齐 docs/openapi/evidsight-v1.yaml ScopeParam） */
export type KnowledgeScope = 'all' | 'mine' | 'public'

/** 知识库对象（对齐 OpenAPI KnowledgeBase schema） */
export type KnowledgeBase = {
  uuid: string
  name: string
  description: string | null
  owner: string
  visibility: 'private' | 'public'
  status: 'active' | 'deleting'
  doc_count: number
  chunk_count: number
  created_at: string
  updated_at: string | null
}

export type KnowledgeBaseCreate = {
  name: string
  description?: string | null
  visibility?: 'private' | 'public'
}

export type KnowledgeBaseUpdate = {
  name?: string | null
  description?: string | null
  visibility?: 'private' | 'public'
}

export type KnowledgeBaseList = {
  total: number
  page: number
  page_size: number
  items: KnowledgeBase[]
}

/** 文档状态六值（对齐 OpenAPI Document.status 枚举） */
export type DocumentStatus =
  'queued' | 'processing' | 'completed' | 'partial' | 'failed' | 'deleting'

export type DocumentFileType = 'pdf' | 'docx' | 'md' | 'txt'

export type Document = {
  uuid: string
  kb_uuid: string
  filename: string
  file_type: DocumentFileType
  file_size: number | null
  status: DocumentStatus
  chunk_count: number
  error_msg: string | null
  created_at: string
  updated_at: string | null
}

export type DocumentList = {
  total: number
  page: number
  page_size: number
  items: Document[]
}

export type DocumentUpload = {
  uuid: string
  kb_uuid: string
  filename: string
  file_type: DocumentFileType
  file_size: number | null
  status: DocumentStatus
}

export type DocumentReprocess = {
  doc_uuid: string
  status: DocumentStatus
}

/** 文档分块：segment_id 为稳定身份，id 为迁移期兼容的内部整数（不作契约） */
export type DocumentChunk = {
  id: number
  segment_id: string
  chunk_index: number
  preview: string
  token_count: number
  metadata?: Record<string, unknown> | null
}

export type DocumentChunkList = {
  total: number
  page: number
  page_size: number
  items: DocumentChunk[]
}

export type DocumentLocation = {
  document_id: string
  segment_id: string
  minimal_excerpt: string
  location: { page_number?: number; section_path?: string[] }
  source_updated_at: string | null
}

type Envelope<T> = { code: string; message: string; data: T }

type ListParams = {
  page?: number
  page_size?: number
}

async function unwrap<T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> {
  const { data } = await promise
  return data.data
}

export type KnowledgeApi = {
  listKnowledgeBases(params?: {
    scope?: KnowledgeScope
    q?: string
    page?: number
    page_size?: number
  }): Promise<KnowledgeBaseList>
  createKnowledgeBase(input: KnowledgeBaseCreate): Promise<KnowledgeBase>
  getKnowledgeBase(kbId: string): Promise<KnowledgeBase>
  updateKnowledgeBase(kbId: string, patch: KnowledgeBaseUpdate): Promise<KnowledgeBase>
  deleteKnowledgeBase(kbId: string): Promise<void>
  listDocuments(
    kbId: string,
    params?: {
      status?: string
      filename?: string
      sort_by?: string
      order?: 'asc' | 'desc'
    } & ListParams,
  ): Promise<DocumentList>
  uploadDocument(kbId: string, file: File, force?: boolean): Promise<DocumentUpload>
  getDocument(documentId: string): Promise<Document>
  deleteDocument(documentId: string): Promise<void>
  getDocumentChunks(documentId: string, params?: ListParams): Promise<DocumentChunkList>
  reprocessDocument(documentId: string): Promise<DocumentReprocess>
  getDocumentLocation(documentId: string, locationId: string): Promise<DocumentLocation>
  withAdapter(adapter: AxiosAdapter): KnowledgeApi
}

function createKnowledgeApi(client: AxiosInstance): KnowledgeApi {
  return {
    async listKnowledgeBases(params = {}) {
      return unwrap(
        client.get<Envelope<KnowledgeBaseList>>('/api/v1/knowledge-bases', {
          params: { scope: 'all', page: 1, page_size: 20, ...params },
        }),
      )
    },

    async createKnowledgeBase(input) {
      return unwrap(client.post<Envelope<KnowledgeBase>>('/api/v1/knowledge-bases', input))
    },

    async getKnowledgeBase(kbId) {
      return unwrap(client.get<Envelope<KnowledgeBase>>(`/api/v1/knowledge-bases/${kbId}`))
    },

    async updateKnowledgeBase(kbId, patch) {
      return unwrap(client.patch<Envelope<KnowledgeBase>>(`/api/v1/knowledge-bases/${kbId}`, patch))
    },

    async deleteKnowledgeBase(kbId) {
      await client.delete(`/api/v1/knowledge-bases/${kbId}`)
    },

    async listDocuments(kbId, params = {}) {
      return unwrap(
        client.get<Envelope<DocumentList>>(`/api/v1/knowledge-bases/${kbId}/documents`, {
          params,
        }),
      )
    },

    async uploadDocument(kbId, file, force = false) {
      const form = new FormData()
      form.append('file', file)
      if (force) {
        form.append('force', 'true')
      }
      return unwrap(
        client.post<Envelope<DocumentUpload>>(`/api/v1/knowledge-bases/${kbId}/documents`, form),
      )
    },

    async getDocument(documentId) {
      return unwrap(client.get<Envelope<Document>>(`/api/v1/documents/${documentId}`))
    },

    async deleteDocument(documentId) {
      await client.delete(`/api/v1/documents/${documentId}`)
    },

    async getDocumentChunks(documentId, params = {}) {
      return unwrap(
        client.get<Envelope<DocumentChunkList>>(`/api/v1/documents/${documentId}/chunks`, {
          params,
        }),
      )
    },

    async reprocessDocument(documentId) {
      return unwrap(
        client.post<Envelope<DocumentReprocess>>(`/api/v1/documents/${documentId}/retry`),
      )
    },

    async getDocumentLocation(documentId, locationId) {
      return unwrap(
        client.get<Envelope<DocumentLocation>>(
          `/api/v1/documents/${documentId}/locations/${locationId}`,
        ),
      )
    },

    withAdapter(adapter) {
      return createKnowledgeApi(createApiClient({ adapter }))
    },
  }
}

export const knowledgeApi: KnowledgeApi = createKnowledgeApi(apiClient)
