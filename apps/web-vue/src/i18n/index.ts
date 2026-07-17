import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'

const LOCALE_STORAGE_KEY = 'musegraph-locale'

export type AppLocale = 'zh-CN' | 'en'

function resolveInitialLocale(): AppLocale {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored === 'zh-CN' || stored === 'en') return stored
  }
  if (typeof navigator !== 'undefined' && /^zh/i.test(navigator.language)) {
    return 'zh-CN'
  }
  return 'zh-CN'
}

function syncHtmlLang(locale: AppLocale) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale === 'zh-CN' ? 'zh-CN' : 'en'
  }
}

const initialLocale = resolveInitialLocale()

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: 'en',
  messages: {
    'zh-CN': zhCN,
    en,
  },
})

syncHtmlLang(initialLocale)

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  }
  syncHtmlLang(locale)
}

export default i18n
