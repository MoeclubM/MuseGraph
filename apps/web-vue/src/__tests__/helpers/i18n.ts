import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import en from '@/i18n/locales/en'

export function createTestI18n(locale: 'zh-CN' | 'en' = 'zh-CN') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: {
      'zh-CN': zhCN,
      en,
    },
  })
}
