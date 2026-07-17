/**
 * Shared control heights aligned with Button size variants (sm / md / lg).
 * Use for Input, Select, DropdownSelect, and native field utilities.
 */
export const controlSizeClasses = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-6 text-[0.95rem]',
} as const

export type ControlSize = keyof typeof controlSizeClasses

/** Extra right padding for native/custom select chevron */
export const selectSizeClasses = {
  sm: 'h-8 px-3 pr-9 text-xs',
  md: 'h-10 px-4 pr-10 text-sm',
  lg: 'h-11 px-6 pr-11 text-[0.95rem]',
} as const

/** DropdownSelect trigger (rounded-md, slightly tighter horizontal padding on sm) */
export const dropdownSelectSizeClasses = {
  sm: 'h-8 px-2.5 text-xs',
  md: 'h-10 px-3 text-sm',
  lg: 'h-11 px-4 text-[0.95rem]',
} as const