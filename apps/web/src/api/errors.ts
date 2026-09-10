import type { AxiosError } from 'axios'

type ApiErrorBody = {
  error?: { message?: string; error_code?: string; request_id?: string }
}

/**
 * 从标准 API 错误信封（API.md §4 `{ error: { message, error_code, ... } }`）提取安全可展示文案。
 * `message` 是面向用户的安全提示（不含正文/堆栈/路径）；拿不到时使用调用方兜底文案，
 * 避免把 axios 原始错误（如 "Request failed with status code 409"）直接展示给用户。
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const axiosErr = err as AxiosError<ApiErrorBody>
  const message = axiosErr?.response?.data?.error?.message
  return message || fallback
}
