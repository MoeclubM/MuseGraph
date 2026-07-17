import { describe, expect, it } from 'vitest'
import zhCN from '@/i18n/locales/zh-CN'
import en from '@/i18n/locales/en'

function collectKeys(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return prefix ? [prefix] : []
  }
  const entries = Object.entries(value as Record<string, unknown>)
  if (entries.length === 0) return prefix ? [prefix] : []
  return entries.flatMap(([key, child]) => collectKeys(child, prefix ? `${prefix}.${key}` : key))
}

describe('i18n locales', () => {
  it('zh-CN and en share the same key structure', () => {
    const zhKeys = new Set(collectKeys(zhCN).sort())
    const enKeys = new Set(collectKeys(en).sort())
    expect([...zhKeys]).toEqual([...enKeys])
  })
})
