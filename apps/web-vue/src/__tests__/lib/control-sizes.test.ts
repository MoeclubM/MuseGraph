import { describe, expect, it } from 'vitest'
import {
  controlSizeClasses,
  dropdownSelectSizeClasses,
  selectSizeClasses,
} from '@/lib/control-sizes'

describe('control-sizes', () => {
  it('aligns sm/md/lg heights with Button tokens', () => {
    expect(controlSizeClasses.sm).toContain('h-8')
    expect(controlSizeClasses.md).toContain('h-10')
    expect(controlSizeClasses.lg).toContain('h-11')
  })

  it('select sizes match control heights', () => {
    expect(selectSizeClasses.sm).toContain('h-8')
    expect(selectSizeClasses.md).toContain('h-10')
    expect(selectSizeClasses.lg).toContain('h-11')
  })

  it('dropdown select sizes match control heights', () => {
    expect(dropdownSelectSizeClasses.sm).toContain('h-8')
    expect(dropdownSelectSizeClasses.md).toContain('h-10')
    expect(dropdownSelectSizeClasses.lg).toContain('h-11')
  })
})