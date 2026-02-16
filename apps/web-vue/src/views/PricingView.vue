<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getPlans } from '@/api/billing'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { Check, Zap } from 'lucide-vue-next'
import type { Plan } from '@/types'

const router = useRouter()
const authStore = useAuthStore()

const plans = ref<Plan[]>([])
const loading = ref(true)
const loadError = ref(false)

const featureLabels: Record<string, string> = {
  max_projects: 'Projects',
  export: 'Export support',
  graph: 'Knowledge graph',
  priority_support: 'Priority support',
}

function formatFeatures(plan: Plan): string[] {
  const features = plan.features
  if (!features) return []
  if (Array.isArray(features)) return features
  const lines: string[] = []
  // Quotas first
  if (plan.quotas) {
    const daily = plan.quotas.daily_requests
    const monthly = plan.quotas.monthly_requests
    if (daily === -1) lines.push('Unlimited daily requests')
    else if (daily) lines.push(`${daily} requests/day`)
    if (monthly === -1) lines.push('Unlimited monthly requests')
    else if (monthly) lines.push(`${monthly} requests/month`)
  }
  // Models
  if (plan.allowed_models?.length) {
    lines.push(`${plan.allowed_models.length} AI models`)
  }
  // Features object
  for (const [key, val] of Object.entries(features)) {
    const label = featureLabels[key] || key.replace(/_/g, ' ')
    if (typeof val === 'boolean') {
      if (val) lines.push(label)
    } else if (typeof val === 'number') {
      lines.push(val === -1 ? `Unlimited ${label.toLowerCase()}` : `${val} ${label.toLowerCase()}`)
    } else {
      lines.push(`${label}: ${val}`)
    }
  }
  return lines
}

function handleSubscribe(plan: Plan) {
  if (!authStore.isAuthenticated) {
    router.push('/login')
    return
  }
  if (plan.price > 0) {
    router.push('/recharge')
  }
}

onMounted(async () => {
  try {
    plans.value = await getPlans()
    loadError.value = false
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppLayout>
    <div class="p-6 max-w-6xl mx-auto">
      <div class="text-center mb-10">
        <h1 class="text-3xl font-bold text-white">Pricing Plans</h1>
        <p class="text-slate-400 mt-2 max-w-lg mx-auto">
          Choose the plan that fits your creative workflow. Upgrade or downgrade anytime.
        </p>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
      </div>

      <div v-else-if="loadError" class="text-center py-20">
        <p class="text-slate-400">Failed to load pricing plans. Please try again later.</p>
      </div>

      <div v-else-if="plans.length === 0" class="text-center py-20">
        <p class="text-slate-400">No plans available at the moment.</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <Card
          v-for="plan in plans"
          :key="plan.id"
          class="flex flex-col relative"
          :class="plan.name === 'pro' ? 'border-blue-500/50 ring-1 ring-blue-500/20' : ''"
        >
          <div
            v-if="plan.name === 'pro'"
            class="absolute -top-3 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-full bg-blue-600 px-3 py-0.5 text-xs font-medium text-white"
          >
            <Zap class="w-3 h-3" />
            Popular
          </div>

          <div class="mb-4">
            <h3 class="text-lg font-semibold text-white">{{ plan.display_name }}</h3>
            <p class="text-sm text-slate-400 mt-1">{{ plan.description }}</p>
          </div>

          <div class="mb-5">
            <span class="text-3xl font-bold text-white">
              {{ plan.price === 0 ? 'Free' : `$${plan.price}` }}
            </span>
            <span v-if="plan.price > 0" class="text-sm text-slate-500">/month</span>
          </div>

          <ul class="space-y-2.5 mb-6 flex-1">
            <li
              v-for="feature in formatFeatures(plan)"
              :key="feature"
              class="flex items-start gap-2 text-sm"
            >
              <Check class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span class="text-slate-300">{{ feature }}</span>
            </li>
          </ul>

          <Button
            :variant="plan.name === 'pro' ? 'primary' : 'secondary'"
            class="w-full"
            @click="handleSubscribe(plan)"
          >
            {{ plan.price === 0 ? 'Get Started' : 'Subscribe' }}
          </Button>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
