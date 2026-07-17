export interface PaletteColors {
  light: Record<string, string>
  dark: Record<string, string>
  swatch: string
}

export type PaletteId = 'amber' | 'blue' | 'emerald' | 'violet' | 'rose' | 'cyan'

export const palettes: Record<PaletteId, PaletteColors> = {
  amber: {
    swatch: '#bc6238',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(188, 98, 56, 0.16)',
      '--muse-accent': '#bc6238',
      '--muse-accent-strong': '#a14e2a',
      '--muse-accent-soft': '#efd5c5',
      '--muse-accent-ink': '#fffaf6',
      // Background colors
      '--muse-bg': '#f4eee6',
      '--muse-bg-soft': '#fbf7f1',
      '--muse-panel': '#f8f3eb',
      '--muse-panel-strong': '#efe5d8',
      '--muse-field': '#fcf8f2',
      '--muse-field-hover': '#f4ebdf',
      '--muse-field-disabled': '#ece3d8',
      '--muse-field-divider': '#d6cabd',
      // Border colors
      '--muse-border': '#d8cec1',
      '--muse-border-strong': '#c7b8a7',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(233, 159, 113, 0.18)',
      '--muse-accent': '#d98859',
      '--muse-accent-strong': '#eba075',
      '--muse-accent-soft': '#382921',
      '--muse-accent-ink': '#1a130f',
      // Background colors
      '--muse-bg': '#141a1d',
      '--muse-bg-soft': '#1a2024',
      '--muse-panel': '#1a2024',
      '--muse-panel-strong': '#22292e',
      '--muse-field': '#20272c',
      '--muse-field-hover': '#252f35',
      '--muse-field-disabled': '#171d21',
      '--muse-field-divider': '#364149',
      // Border colors
      '--muse-border': '#2f393f',
      '--muse-border-strong': '#3f4b52',
    },
  },
  blue: {
    swatch: '#3b82f6',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(59, 130, 246, 0.16)',
      '--muse-accent': '#3b82f6',
      '--muse-accent-strong': '#2563eb',
      '--muse-accent-soft': '#dbeafe',
      '--muse-accent-ink': '#ffffff',
      // Background colors
      '--muse-bg': '#f0f5ff',
      '--muse-bg-soft': '#f8faff',
      '--muse-panel': '#f4f8ff',
      '--muse-panel-strong': '#e8f0fe',
      '--muse-field': '#fafcff',
      '--muse-field-hover': '#f0f5ff',
      '--muse-field-disabled': '#e8f0fe',
      '--muse-field-divider': '#d0dff5',
      // Border colors
      '--muse-border': '#c7d9f5',
      '--muse-border-strong': '#b0c9f0',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(96, 165, 250, 0.18)',
      '--muse-accent': '#60a5fa',
      '--muse-accent-strong': '#93bbfd',
      '--muse-accent-soft': '#1e293b',
      '--muse-accent-ink': '#0f172a',
      // Background colors
      '--muse-bg': '#0f172a',
      '--muse-bg-soft': '#1e293b',
      '--muse-panel': '#1e293b',
      '--muse-panel-strong': '#273548',
      '--muse-field': '#243244',
      '--muse-field-hover': '#2d3d52',
      '--muse-field-disabled': '#172033',
      '--muse-field-divider': '#334d6e',
      // Border colors
      '--muse-border': '#334d6e',
      '--muse-border-strong': '#456285',
    },
  },
  emerald: {
    swatch: '#10b981',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(16, 185, 129, 0.16)',
      '--muse-accent': '#10b981',
      '--muse-accent-strong': '#059669',
      '--muse-accent-soft': '#d1fae5',
      '--muse-accent-ink': '#ffffff',
      // Background colors
      '--muse-bg': '#f0fdf4',
      '--muse-bg-soft': '#f5fdf8',
      '--muse-panel': '#f4fcf7',
      '--muse-panel-strong': '#e6f9ee',
      '--muse-field': '#f9fdfb',
      '--muse-field-hover': '#f0fdf4',
      '--muse-field-disabled': '#e6f9ee',
      '--muse-field-divider': '#c6f0d9',
      // Border colors
      '--muse-border': '#b5e8ce',
      '--muse-border-strong': '#9fdfc3',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(52, 211, 153, 0.18)',
      '--muse-accent': '#34d399',
      '--muse-accent-strong': '#6ee7b7',
      '--muse-accent-soft': '#064e3b',
      '--muse-accent-ink': '#022c22',
      // Background colors
      '--muse-bg': '#022c22',
      '--muse-bg-soft': '#064e3b',
      '--muse-panel': '#064e3b',
      '--muse-panel-strong': '#0d6b4f',
      '--muse-field': '#0a5e45',
      '--muse-field-hover': '#117a5a',
      '--muse-field-disabled': '#033a2d',
      '--muse-field-divider': '#1a8a68',
      // Border colors
      '--muse-border': '#1a8a68',
      '--muse-border-strong': '#22a37c',
    },
  },
  violet: {
    swatch: '#8b5cf6',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(139, 92, 246, 0.16)',
      '--muse-accent': '#8b5cf6',
      '--muse-accent-strong': '#7c3aed',
      '--muse-accent-soft': '#ede9fe',
      '--muse-accent-ink': '#ffffff',
      // Background colors
      '--muse-bg': '#f5f3ff',
      '--muse-bg-soft': '#faf8ff',
      '--muse-panel': '#f8f6ff',
      '--muse-panel-strong': '#f0edfe',
      '--muse-field': '#fcfbff',
      '--muse-field-hover': '#f5f3ff',
      '--muse-field-disabled': '#f0edfe',
      '--muse-field-divider': '#d8d0fc',
      // Border colors
      '--muse-border': '#c9bdfc',
      '--muse-border-strong': '#b5a8f8',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(167, 139, 250, 0.18)',
      '--muse-accent': '#a78bfa',
      '--muse-accent-strong': '#c4b5fd',
      '--muse-accent-soft': '#2e1065',
      '--muse-accent-ink': '#1e1b4b',
      // Background colors
      '--muse-bg': '#1e1b4b',
      '--muse-bg-soft': '#2e1065',
      '--muse-panel': '#2e1065',
      '--muse-panel-strong': '#3b1580',
      '--muse-field': '#351273',
      '--muse-field-hover': '#441a8f',
      '--muse-field-disabled': '#230d52',
      '--muse-field-divider': '#5220a8',
      // Border colors
      '--muse-border': '#5220a8',
      '--muse-border-strong': '#6228c2',
    },
  },
  rose: {
    swatch: '#f43f5e',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(244, 63, 94, 0.16)',
      '--muse-accent': '#f43f5e',
      '--muse-accent-strong': '#e11d48',
      '--muse-accent-soft': '#ffe4e6',
      '--muse-accent-ink': '#ffffff',
      // Background colors
      '--muse-bg': '#fff1f2',
      '--muse-bg-soft': '#fff8f8',
      '--muse-panel': '#fef4f5',
      '--muse-panel-strong': '#ffe8ea',
      '--muse-field': '#fffafb',
      '--muse-field-hover': '#fff1f2',
      '--muse-field-disabled': '#ffe8ea',
      '--muse-field-divider': '#fcc8cc',
      // Border colors
      '--muse-border': '#f9b4ba',
      '--muse-border-strong': '#f59da5',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(251, 113, 133, 0.18)',
      '--muse-accent': '#fb7185',
      '--muse-accent-strong': '#fda4af',
      '--muse-accent-soft': '#4c0519',
      '--muse-accent-ink': '#1f0310',
      // Background colors
      '--muse-bg': '#1f0310',
      '--muse-bg-soft': '#4c0519',
      '--muse-panel': '#4c0519',
      '--muse-panel-strong': '#5f0a20',
      '--muse-field': '#56081c',
      '--muse-field-hover': '#6d0f28',
      '--muse-field-disabled': '#3d0414',
      '--muse-field-divider': '#851533',
      // Border colors
      '--muse-border': '#851533',
      '--muse-border-strong': '#9d1c3e',
    },
  },
  cyan: {
    swatch: '#06b6d4',
    light: {
      // Accent colors
      '--muse-ring': 'rgba(6, 182, 212, 0.16)',
      '--muse-accent': '#06b6d4',
      '--muse-accent-strong': '#0891b2',
      '--muse-accent-soft': '#cffafe',
      '--muse-accent-ink': '#ffffff',
      // Background colors
      '--muse-bg': '#ecfeff',
      '--muse-bg-soft': '#f5feff',
      '--muse-panel': '#f4fcff',
      '--muse-panel-strong': '#e0f9fe',
      '--muse-field': '#f9feff',
      '--muse-field-hover': '#ecfeff',
      '--muse-field-disabled': '#e0f9fe',
      '--muse-field-divider': '#b5f0fc',
      // Border colors
      '--muse-border': '#a1e8fa',
      '--muse-border-strong': '#88e0f8',
    },
    dark: {
      // Accent colors
      '--muse-ring': 'rgba(34, 211, 238, 0.18)',
      '--muse-accent': '#22d3ee',
      '--muse-accent-strong': '#67e8f9',
      '--muse-accent-soft': '#083344',
      '--muse-accent-ink': '#042f2e',
      // Background colors
      '--muse-bg': '#042f2e',
      '--muse-bg-soft': '#083344',
      '--muse-panel': '#083344',
      '--muse-panel-strong': '#0c4256',
      '--muse-field': '#0a3c4d',
      '--muse-field-hover': '#104d62',
      '--muse-field-disabled': '#062a38',
      '--muse-field-divider': '#14607a',
      // Border colors
      '--muse-border': '#14607a',
      '--muse-border-strong': '#1a7592',
    },
  },
}

export const paletteLabels: Record<PaletteId, string> = {
  amber: 'Amber',
  blue: 'Blue',
  emerald: 'Emerald',
  violet: 'Violet',
  rose: 'Rose',
  cyan: 'Cyan',
}
