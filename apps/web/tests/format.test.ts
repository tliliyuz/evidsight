import { describe, expect, it } from 'vitest'

import { formatTimestamp } from '@/features/knowledge/format'

describe('formatTimestamp 绝对时间戳（对齐原型「2026-07-31 12:18」口径）', () => {
  it('本地时区格式化为 YYYY-MM-DD HH:mm', () => {
    expect(formatTimestamp(new Date(2026, 6, 31, 12, 18))).toBe('2026-07-31 12:18')
  })

  it('ISO 字符串与 Date 实例同口径', () => {
    const iso = '2026-08-08T00:00:00Z'
    expect(formatTimestamp(iso)).toBe(formatTimestamp(new Date(iso)))
  })

  it('空值与非法输入返回占位符 —', () => {
    expect(formatTimestamp(null)).toBe('—')
    expect(formatTimestamp('not-a-date')).toBe('—')
  })
})
