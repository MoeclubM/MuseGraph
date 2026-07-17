import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { initTheme } from './composables/useTheme'
import i18n from './i18n'
import './style.css'
import { useAuthStore } from './stores/auth'

initTheme()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(i18n)
await useAuthStore(pinia).init()
app.use(router)
app.mount('#app')
