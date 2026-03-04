import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/admin/login',
      name: 'admin-login',
      component: () => import('@/views/AdminLoginView.vue'),
      meta: { adminGuest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { guest: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { auth: true },
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/views/ProjectsView.vue'),
      meta: { auth: true },
    },
    {
      path: '/projects/:id',
      name: 'project',
      component: () => import('@/views/ProjectView.vue'),
      meta: { auth: true },
    },
    {
      path: '/projects/:id/graph',
      name: 'graph',
      component: () => import('@/views/GraphView.vue'),
      meta: { auth: true },
    },
    {
      path: '/projects/:id/workflow',
      name: 'workflow',
      redirect: (to) => ({ path: `/projects/${to.params.id}` }),
      meta: { auth: true },
    },
    {
      path: '/simulation/:simulationId',
      name: 'simulation',
      component: () => import('@/views/SimulationView.vue'),
      meta: { auth: true },
    },
    {
      path: '/simulation/:simulationId/start',
      name: 'simulation-run',
      component: () => import('@/views/SimulationRunView.vue'),
      meta: { auth: true },
    },
    {
      path: '/report/:reportId',
      name: 'report',
      component: () => import('@/views/ReportView.vue'),
      meta: { auth: true },
    },
    {
      path: '/interaction/:reportId',
      name: 'interaction',
      component: () => import('@/views/InteractionView.vue'),
      meta: { auth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { auth: true, adminAuth: true },
    },
    {
      path: '/pricing',
      name: 'pricing',
      component: () => import('@/views/PricingView.vue'),
    },
    {
      path: '/recharge',
      name: 'recharge',
      component: () => import('@/views/RechargeView.vue'),
      meta: { auth: true },
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  const isAdminPath = to.path.startsWith('/admin')

  if (to.meta.adminGuest) {
    if (authStore.isAuthenticated && authStore.isAdmin) {
      return next({ name: 'admin' })
    }
    return next()
  }

  if (to.meta.auth && !authStore.isAuthenticated) {
    return next({
      name: isAdminPath ? 'admin-login' : 'login',
      query: { redirect: to.fullPath },
    })
  }

  if (to.meta.adminAuth && !authStore.isAdmin) {
    return next({ name: 'dashboard' })
  }

  if (to.meta.guest && authStore.isAuthenticated) {
    return next({ name: 'dashboard' })
  }

  next()
})

export default router
