import type { UserSummary } from '@/api/auth'
import type { KnowledgeBase } from '@/api/knowledge'

/**
 * 知识库权限纯函数封装（PRD §8.2 权限矩阵）。
 * 权限判断必须基于服务端身份（/me 的 Platform User UUID + role）与资源字段（kb.owner），
 * 不得按 visibility 推断上传权限，也不得只靠视觉禁用。
 */

/** owner：资源 owner 的 Platform User UUID 与当前用户一致。 */
export function isOwner(kb: Pick<KnowledgeBase, 'owner'>, user: UserSummary | null): boolean {
  return user !== null && kb.owner === user.id
}

/** 编辑元数据 / 删除知识库：owner 或 admin 治理（PRD §8.2）。 */
export function canManageKb(kb: Pick<KnowledgeBase, 'owner'>, user: UserSummary | null): boolean {
  return isOwner(kb, user) || user?.role === 'admin'
}

/** 上传文档 / 重试：仅 owner（admin 非 owner 不得代替上传，PRD §8.2）。 */
export function canUploadToKb(
  kb: Pick<KnowledgeBase, 'owner' | 'status'>,
  user: UserSummary | null,
): boolean {
  return kb.status === 'active' && isOwner(kb, user)
}
