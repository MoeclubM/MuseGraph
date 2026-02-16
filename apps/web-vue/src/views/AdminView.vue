<script setup lang="ts">
import { ref, reactive, onMounted, type Component } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import {
  getStats, getUsers, getGroups, updateUserGroup,
  createGroup, updateGroup, deleteGroup,
  getPlans, createPlan, updatePlan, deletePlan,
  getProviders, createProvider, updateProvider, deleteProvider,
  getModelPermissions, createModelPermission, updateModelPermission, deleteModelPermission,
} from '@/api/admin'
import type { StatsResponse, UserGroup, UserListResponse, Plan, Provider, ModelPermission } from '@/types'
import {
  Users, FolderOpen, Zap, DollarSign, ChevronLeft, ChevronRight,
  Plus, Pencil, Trash2, X, BarChart3, Shield, CreditCard, Server, Key,
  PackageOpen, Database, FileQuestion,
} from 'lucide-vue-next'

type TabKey = 'overview' | 'users' | 'groups' | 'plans' | 'providers' | 'models'
const tabs: { key: TabKey; label: string; icon: Component }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'users', label: 'Users', icon: Users },
  { key: 'groups', label: 'Groups', icon: Shield },
  { key: 'plans', label: 'Plans', icon: CreditCard },
  { key: 'providers', label: 'Providers', icon: Server },
  { key: 'models', label: 'Model Permissions', icon: Key },
]

const activeTab = ref<TabKey>('overview')
const stats = ref<StatsResponse | null>(null)
const usersData = ref<UserListResponse | null>(null)
const groups = ref<UserGroup[]>([])
const loading = ref(true)
const page = ref(1)
const pageSize = 20

// Delete confirmation state: maps entity id -> true when first click happened
const deleteConfirm = reactive<Record<string, boolean>>({})
let deleteConfirmTimer: ReturnType<typeof setTimeout> | null = null

function requestDelete(id: string, deleteFn: (id: string) => Promise<void>) {
  if (deleteConfirm[id]) {
    // Second click - actually delete
    delete deleteConfirm[id]
    deleteFn(id)
  } else {
    // First click - show confirm
    deleteConfirm[id] = true
    if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer)
    deleteConfirmTimer = setTimeout(() => { delete deleteConfirm[id] }, 3000)
  }
}

// Groups CRUD
const showGroupForm = ref(false)
const editingGroup = ref<UserGroup | null>(null)
const groupForm = ref({
  name: '', display_name: '', description: '', color: '#3b82f6',
  allowed_models: '' , quotas: '{"daily_requests": 100, "monthly_requests": 3000}',
  features: '{"max_projects": 10, "export": true, "graph": false, "priority_support": false}',
  price: 0, sort_order: 0, is_active: true, is_default: false,
})

function openGroupCreate() {
  editingGroup.value = null
  groupForm.value = {
    name: '', display_name: '', description: '', color: '#3b82f6',
    allowed_models: '', quotas: '{"daily_requests": 100, "monthly_requests": 3000}',
    features: '{"max_projects": 10, "export": true, "graph": false, "priority_support": false}',
    price: 0, sort_order: 0, is_active: true, is_default: false,
  }
  showGroupForm.value = true
}
function openGroupEdit(g: UserGroup) {
  editingGroup.value = g
  groupForm.value = {
    name: g.name, display_name: g.display_name, description: g.description || '',
    color: g.color || '#3b82f6',
    allowed_models: (g.allowed_models ?? []).join(', '),
    quotas: JSON.stringify(g.quotas ?? {}, null, 2),
    features: JSON.stringify(g.features ?? {}, null, 2),
    price: g.price ?? 0, sort_order: g.sort_order, is_active: g.is_active, is_default: g.is_default,
  }
  showGroupForm.value = true
}
async function saveGroup() {
  const payload: any = {
    name: groupForm.value.name,
    display_name: groupForm.value.display_name,
    description: groupForm.value.description || null,
    color: groupForm.value.color || null,
    allowed_models: groupForm.value.allowed_models ? groupForm.value.allowed_models.split(',').map(s => s.trim()).filter(Boolean) : [],
    quotas: JSON.parse(groupForm.value.quotas || '{}'),
    features: JSON.parse(groupForm.value.features || '{}'),
    price: groupForm.value.price,
    sort_order: groupForm.value.sort_order,
    is_active: groupForm.value.is_active,
    is_default: groupForm.value.is_default,
  }
  try {
    if (editingGroup.value) await updateGroup(editingGroup.value.id, payload)
    else await createGroup(payload)
    showGroupForm.value = false
    await loadGroups()
  } catch { /* */ }
}
async function handleDeleteGroup(id: string) {
  try { await deleteGroup(id); await loadGroups() } catch { /* */ }
}

// Plans
const plans = ref<Plan[]>([])
const showPlanForm = ref(false)
const editingPlan = ref<Plan | null>(null)
const planForm = ref({
  name: '', display_name: '', description: '', price: 0, original_price: null as number | null,
  duration: 30, target_group_id: '', features: '[]', quotas: '{}', allowed_models: '',
  is_active: true, sort_order: 0,
})

// Providers
const providers = ref<Provider[]>([])
const showProviderForm = ref(false)
const editingProvider = ref<Provider | null>(null)
const providerForm = ref({
  name: '', provider: 'openai', api_key: '', base_url: '', is_active: true, priority: 0,
})
const providerModelTags = ref<string[]>([])
const providerModelInput = ref('')

function addProviderModelTag() {
  const val = providerModelInput.value.trim()
  if (val && !providerModelTags.value.includes(val)) {
    providerModelTags.value.push(val)
  }
  providerModelInput.value = ''
}
function removeProviderModelTag(index: number) {
  providerModelTags.value.splice(index, 1)
}
function handleProviderModelKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    addProviderModelTag()
  }
  if (e.key === 'Backspace' && !providerModelInput.value && providerModelTags.value.length) {
    providerModelTags.value.pop()
  }
}

// Model Permissions
const modelPerms = ref<ModelPermission[]>([])
const showPermForm = ref(false)
const editingPerm = ref<ModelPermission | null>(null)
const permForm = ref({
  model: '', group_id: '', daily_limit: 100, monthly_limit: 3000, is_active: true,
})

async function loadStats() {
  try { stats.value = await getStats() } catch { /* */ }
}
async function loadUsers() {
  try { usersData.value = await getUsers(page.value, pageSize) } catch { /* */ }
}
async function loadGroups() {
  try { groups.value = await getGroups() } catch { /* */ }
}
async function loadPlans() {
  try { plans.value = await getPlans() } catch { /* */ }
}
async function loadProviders() {
  try { providers.value = await getProviders() } catch { /* */ }
}
async function loadModelPerms() {
  try { modelPerms.value = await getModelPermissions() } catch { /* */ }
}

async function handleChangeGroup(userId: string, groupId: string) {
  try { await updateUserGroup(userId, groupId); await loadUsers() } catch { /* */ }
}

// Plan CRUD
function openPlanCreate() {
  editingPlan.value = null
  planForm.value = { name: '', display_name: '', description: '', price: 0, original_price: null, duration: 30, target_group_id: '', features: '[]', quotas: '{}', allowed_models: '', is_active: true, sort_order: 0 }
  showPlanForm.value = true
}
function openPlanEdit(p: Plan) {
  editingPlan.value = p
  planForm.value = {
    name: p.name, display_name: p.display_name, description: p.description || '',
    price: p.price, original_price: p.original_price, duration: p.duration,
    target_group_id: (p as any).target_group_id || '',
    features: JSON.stringify(p.features ?? []),
    quotas: JSON.stringify(p.quotas ?? {}),
    allowed_models: (p.allowed_models ?? []).join(', '),
    is_active: p.is_active, sort_order: p.sort_order,
  }
  showPlanForm.value = true
}
async function savePlan() {
  const payload: any = {
    ...planForm.value,
    features: JSON.parse(planForm.value.features || '[]'),
    quotas: JSON.parse(planForm.value.quotas || '{}'),
    allowed_models: planForm.value.allowed_models ? planForm.value.allowed_models.split(',').map(s => s.trim()).filter(Boolean) : [],
    target_group_id: planForm.value.target_group_id || null,
    original_price: planForm.value.original_price || null,
  }
  try {
    if (editingPlan.value) await updatePlan(editingPlan.value.id, payload)
    else await createPlan(payload)
    showPlanForm.value = false
    await loadPlans()
  } catch { /* */ }
}
async function handleDeletePlan(id: string) {
  try { await deletePlan(id); await loadPlans() } catch { /* */ }
}

// Provider CRUD
function openProviderCreate() {
  editingProvider.value = null
  providerForm.value = { name: '', provider: 'openai', api_key: '', base_url: '', is_active: true, priority: 0 }
  providerModelTags.value = []
  providerModelInput.value = ''
  showProviderForm.value = true
}
function openProviderEdit(p: Provider) {
  editingProvider.value = p
  providerForm.value = {
    name: p.name, provider: p.provider, api_key: '', base_url: p.base_url || '',
    is_active: p.is_active, priority: p.priority,
  }
  providerModelTags.value = [...(p.models ?? [])]
  providerModelInput.value = ''
  showProviderForm.value = true
}
async function saveProvider() {
  const payload: any = {
    ...providerForm.value,
    models: providerModelTags.value,
    base_url: providerForm.value.base_url || null,
  }
  if (editingProvider.value && !payload.api_key) delete payload.api_key
  try {
    if (editingProvider.value) await updateProvider(editingProvider.value.id, payload)
    else await createProvider(payload)
    showProviderForm.value = false
    await loadProviders()
  } catch { /* */ }
}
async function handleDeleteProvider(id: string) {
  try { await deleteProvider(id); await loadProviders() } catch { /* */ }
}

// Model Permission CRUD
function openPermCreate() {
  editingPerm.value = null
  permForm.value = { model: '', group_id: '', daily_limit: 100, monthly_limit: 3000, is_active: true }
  showPermForm.value = true
}
function openPermEdit(p: ModelPermission) {
  editingPerm.value = p
  permForm.value = { model: p.model, group_id: p.group_id, daily_limit: p.daily_limit, monthly_limit: p.monthly_limit, is_active: p.is_active }
  showPermForm.value = true
}
async function savePerm() {
  try {
    if (editingPerm.value) await updateModelPermission(editingPerm.value.id, permForm.value)
    else await createModelPermission(permForm.value)
    showPermForm.value = false
    await loadModelPerms()
  } catch { /* */ }
}
async function handleDeletePerm(id: string) {
  try { await deleteModelPermission(id); await loadModelPerms() } catch { /* */ }
}

function groupName(gid: string) {
  return groups.value.find(g => g.id === gid)?.display_name || gid
}

function nextPage() {
  if (usersData.value && page.value * pageSize < usersData.value.total) { page.value++; loadUsers() }
}
function prevPage() {
  if (page.value > 1) { page.value--; loadUsers() }
}
function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

onMounted(async () => {
  loading.value = true
  await Promise.all([loadStats(), loadUsers(), loadGroups(), loadPlans(), loadProviders(), loadModelPerms()])
  loading.value = false
})
</script>

<template>
  <AppLayout>
    <div class="p-6 max-w-6xl mx-auto">
      <div class="mb-6">
        <h1 class="text-2xl font-bold text-white">Admin Panel</h1>
        <p class="text-sm text-slate-400 mt-1">System overview and management</p>
      </div>

      <!-- Tabs -->
      <div class="flex gap-1 mb-6 border-b border-slate-700/50 overflow-x-auto">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors"
          :class="activeTab === t.key ? 'text-blue-400 border-b-2 border-blue-400' : 'text-slate-400 hover:text-slate-200'"
          @click="activeTab = t.key"
        >
          <component :is="t.icon" class="w-4 h-4" />
          {{ t.label }}
        </button>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
      </div>

      <!-- Overview Tab -->
      <div v-else-if="activeTab === 'overview'" class="space-y-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600/20">
                <Users class="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <p class="text-2xl font-bold text-white">{{ stats?.total_users ?? 0 }}</p>
                <p class="text-xs text-slate-400">Total Users</p>
              </div>
            </div>
          </Card>
          <Card>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-600/20">
                <FolderOpen class="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <p class="text-2xl font-bold text-white">{{ stats?.total_projects ?? 0 }}</p>
                <p class="text-xs text-slate-400">Total Projects</p>
              </div>
            </div>
          </Card>
          <Card>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-600/20">
                <Zap class="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <p class="text-2xl font-bold text-white">{{ stats?.total_operations ?? 0 }}</p>
                <p class="text-xs text-slate-400">Total Operations</p>
              </div>
            </div>
          </Card>
          <Card>
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-600/20">
                <DollarSign class="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <p class="text-2xl font-bold text-white">{{ (stats?.total_revenue ?? 0).toFixed(2) }}</p>
                <p class="text-xs text-slate-400">Total Revenue</p>
              </div>
            </div>
          </Card>
        </div>

        <!-- Daily Active Users -->
        <Card v-if="stats">
          <h3 class="text-sm font-semibold text-slate-300 mb-3">Activity</h3>
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-600/20">
              <Users class="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <p class="text-2xl font-bold text-white">{{ stats.daily_active_users }}</p>
              <p class="text-xs text-slate-400">Daily Active Users</p>
            </div>
          </div>
        </Card>
      </div>

      <!-- Users Tab -->
      <div v-else-if="activeTab === 'users'">
        <Card :padding="false">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-slate-700/50">
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">User</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Email</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Role</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Group</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Status</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Joined</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="user in usersData?.users ?? []"
                  :key="user.id"
                  class="border-b border-slate-700/30 hover:bg-slate-800/50 transition-colors"
                >
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <div class="flex h-7 w-7 items-center justify-center rounded-full bg-slate-700 text-xs font-medium text-slate-300">
                        {{ user.username.charAt(0).toUpperCase() }}
                      </div>
                      <span class="text-slate-200">{{ user.username }}</span>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-slate-400">{{ user.email }}</td>
                  <td class="px-4 py-3">
                    <span
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                      :class="user.role === 'ADMIN' ? 'bg-amber-900/50 text-amber-300' : 'bg-slate-700 text-slate-300'"
                    >
                      {{ user.role }}
                    </span>
                  </td>
                  <td class="px-4 py-3">
                    <select
                      :value="user.group_id || ''"
                      class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 focus:border-blue-500 focus:outline-none"
                      @change="(e) => handleChangeGroup(user.id, (e.target as HTMLSelectElement).value)"
                    >
                      <option value="">None</option>
                      <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.display_name }}</option>
                    </select>
                  </td>
                  <td class="px-4 py-3">
                    <span
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                      :class="user.status === 'ACTIVE' ? 'bg-emerald-900/50 text-emerald-300' : 'bg-red-900/50 text-red-300'"
                    >
                      {{ user.status }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-slate-500 text-xs">{{ formatDate(user.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="usersData" class="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <span class="text-xs text-slate-500">
              Showing {{ (page - 1) * pageSize + 1 }}-{{ Math.min(page * pageSize, usersData.total) }} of {{ usersData.total }}
            </span>
            <div class="flex gap-1">
              <Button variant="ghost" size="sm" :disabled="page <= 1" @click="prevPage">
                <ChevronLeft class="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="sm" :disabled="page * pageSize >= usersData.total" @click="nextPage">
                <ChevronRight class="w-4 h-4" />
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <!-- Groups Tab -->
      <div v-else-if="activeTab === 'groups'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold text-white">User Groups</h2>
          <Button variant="primary" size="sm" @click="openGroupCreate"><Plus class="w-4 h-4" /> New Group</Button>
        </div>

        <!-- Group Form -->
        <Card v-if="showGroupForm" class="space-y-3">
          <div class="flex justify-between items-center mb-2">
            <h3 class="text-sm font-semibold text-slate-200">{{ editingGroup ? 'Edit Group' : 'Create Group' }}</h3>
            <button class="text-slate-500 hover:text-slate-300" @click="showGroupForm = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Name (slug)</label>
              <input v-model="groupForm.name" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Display Name</label>
              <input v-model="groupForm.display_name" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Description</label>
              <input v-model="groupForm.description" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Color</label>
              <div class="flex items-center gap-2">
                <input v-model="groupForm.color" type="color" class="h-8 w-10 rounded border border-slate-700 bg-slate-800 cursor-pointer" />
                <input v-model="groupForm.color" class="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
              </div>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Price</label>
              <input v-model.number="groupForm.price" type="number" step="0.01" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Sort Order</label>
              <input v-model.number="groupForm.sort_order" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Allowed Models (comma-separated)</label>
              <input v-model="groupForm.allowed_models" placeholder="gpt-4o, claude-3-5-sonnet" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Quotas (JSON)</label>
              <textarea v-model="groupForm.quotas" rows="3" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Features (JSON)</label>
              <textarea v-model="groupForm.features" rows="3" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="flex items-center gap-4">
              <div class="flex items-center gap-2">
                <input v-model="groupForm.is_active" type="checkbox" class="rounded border-slate-600" />
                <label class="text-sm text-slate-300">Active</label>
              </div>
              <div class="flex items-center gap-2">
                <input v-model="groupForm.is_default" type="checkbox" class="rounded border-slate-600" />
                <label class="text-sm text-slate-300">Default Group</label>
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" @click="showGroupForm = false">Cancel</Button>
            <Button variant="primary" size="sm" @click="saveGroup">{{ editingGroup ? 'Update' : 'Create' }}</Button>
          </div>
        </Card>

        <!-- Group Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card v-for="group in groups" :key="group.id" class="!pl-0 overflow-hidden">
            <div class="flex h-full">
              <div class="w-1 shrink-0 rounded-l" :style="{ backgroundColor: group.color || '#475569' }" />
              <div class="flex-1 pl-4">
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center gap-2">
                    <h3 class="text-base font-semibold text-slate-100">{{ group.display_name }}</h3>
                    <span v-if="group.is_default" class="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-900/50 text-blue-300">Default</span>
                  </div>
                  <div class="flex items-center gap-1">
                    <span class="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-400 mr-1">{{ group.name }}</span>
                    <button class="text-slate-500 hover:text-blue-400 p-1" @click="openGroupEdit(group)"><Pencil class="w-3.5 h-3.5" /></button>
                    <button
                      v-if="!group.is_default"
                      class="p-1 text-xs transition-colors"
                      :class="deleteConfirm[group.id] ? 'text-red-400 font-medium' : 'text-slate-500 hover:text-red-400'"
                      @click="requestDelete(group.id, handleDeleteGroup)"
                    >
                      <span v-if="deleteConfirm[group.id]">Confirm?</span>
                      <Trash2 v-else class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <p v-if="group.description" class="text-sm text-slate-400 mb-3">{{ group.description }}</p>
                <div class="space-y-1.5 text-sm">
                  <div v-if="group.price !== null" class="flex justify-between">
                    <span class="text-slate-500">Price</span>
                    <span class="text-slate-300">{{ group.price === 0 ? 'Free' : `$${group.price}` }}</span>
                  </div>
                  <div v-if="group.quotas" class="pt-1">
                    <span class="text-xs text-slate-500">Quotas:</span>
                    <div class="mt-1 space-y-1">
                      <div v-for="(value, key) in group.quotas" :key="String(key)" class="flex justify-between">
                        <span class="text-slate-500">{{ key }}</span>
                        <span class="text-slate-300">{{ value }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="group.allowed_models?.length" class="pt-2">
                    <span class="text-xs text-slate-500">Allowed Models:</span>
                    <div class="flex flex-wrap gap-1 mt-1">
                      <span
                        v-for="model in group.allowed_models"
                        :key="model"
                        class="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400"
                      >
                        {{ model }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>

        <!-- Empty state -->
        <div v-if="groups.length === 0" class="flex flex-col items-center justify-center py-16 text-slate-500">
          <Shield class="w-10 h-10 mb-3 text-slate-600" />
          <p class="text-sm">No user groups configured</p>
          <p class="text-xs text-slate-600 mt-1">Create a group to get started</p>
        </div>
      </div>

      <!-- Plans Tab -->
      <div v-else-if="activeTab === 'plans'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold text-white">Subscription Plans</h2>
          <Button variant="primary" size="sm" @click="openPlanCreate"><Plus class="w-4 h-4" /> New Plan</Button>
        </div>

        <!-- Plan Form Modal -->
        <Card v-if="showPlanForm" class="space-y-3">
          <div class="flex justify-between items-center mb-2">
            <h3 class="text-sm font-semibold text-slate-200">{{ editingPlan ? 'Edit Plan' : 'Create Plan' }}</h3>
            <button class="text-slate-500 hover:text-slate-300" @click="showPlanForm = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Name (slug)</label>
              <input v-model="planForm.name" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Display Name</label>
              <input v-model="planForm.display_name" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Description</label>
              <input v-model="planForm.description" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Price</label>
              <input v-model.number="planForm.price" type="number" step="0.01" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Original Price</label>
              <input v-model.number="planForm.original_price" type="number" step="0.01" placeholder="Optional" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Duration (days)</label>
              <input v-model.number="planForm.duration" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Target Group</label>
              <select v-model="planForm.target_group_id" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none">
                <option value="">None</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.display_name }}</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Allowed Models (comma-separated)</label>
              <input v-model="planForm.allowed_models" placeholder="gpt-4o, claude-3-5-sonnet" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Sort Order</label>
              <input v-model.number="planForm.sort_order" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Features (JSON)</label>
              <textarea v-model="planForm.features" rows="2" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Quotas (JSON)</label>
              <textarea v-model="planForm.quotas" rows="2" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 font-mono focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="flex items-center gap-2">
              <input v-model="planForm.is_active" type="checkbox" class="rounded border-slate-600" />
              <label class="text-sm text-slate-300">Active</label>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" @click="showPlanForm = false">Cancel</Button>
            <Button variant="primary" size="sm" @click="savePlan">{{ editingPlan ? 'Update' : 'Create' }}</Button>
          </div>
        </Card>

        <!-- Plans Table -->
        <Card :padding="false">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-slate-700/50">
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Name</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Price</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Duration</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Group</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Status</th>
                  <th class="text-right px-4 py-3 text-xs font-medium text-slate-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in plans" :key="p.id" class="border-b border-slate-700/30 hover:bg-slate-800/50">
                  <td class="px-4 py-3">
                    <div class="text-slate-200 font-medium">{{ p.display_name }}</div>
                    <div class="text-xs text-slate-500">{{ p.name }}</div>
                  </td>
                  <td class="px-4 py-3 text-slate-300">
                    {{ p.price === 0 ? 'Free' : `$${p.price}` }}
                    <span v-if="p.original_price" class="text-xs text-slate-500 line-through ml-1">${{ p.original_price }}</span>
                  </td>
                  <td class="px-4 py-3 text-slate-400">{{ p.duration === 0 ? 'Forever' : `${p.duration}d` }}</td>
                  <td class="px-4 py-3 text-slate-400">{{ (p as any).target_group_id ? groupName((p as any).target_group_id) : '—' }}</td>
                  <td class="px-4 py-3">
                    <span :class="p.is_active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-slate-700 text-slate-400'" class="text-xs px-2 py-0.5 rounded-full">
                      {{ p.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <button class="text-slate-500 hover:text-blue-400 mr-2" @click="openPlanEdit(p)"><Pencil class="w-3.5 h-3.5" /></button>
                    <button
                      class="text-xs transition-colors"
                      :class="deleteConfirm[p.id] ? 'text-red-400 font-medium' : 'text-slate-500 hover:text-red-400'"
                      @click="requestDelete(p.id, handleDeletePlan)"
                    >
                      <span v-if="deleteConfirm[p.id]">Confirm?</span>
                      <Trash2 v-else class="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
                <tr v-if="plans.length === 0">
                  <td colspan="6" class="px-4 py-12 text-center">
                    <div class="flex flex-col items-center text-slate-500">
                      <CreditCard class="w-8 h-8 mb-2 text-slate-600" />
                      <p class="text-sm">No plans configured</p>
                      <p class="text-xs text-slate-600 mt-1">Create a subscription plan to get started</p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <!-- Providers Tab -->
      <div v-else-if="activeTab === 'providers'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold text-white">AI Providers</h2>
          <Button variant="primary" size="sm" @click="openProviderCreate"><Plus class="w-4 h-4" /> New Provider</Button>
        </div>

        <!-- Provider Form -->
        <Card v-if="showProviderForm" class="space-y-3">
          <div class="flex justify-between items-center mb-2">
            <h3 class="text-sm font-semibold text-slate-200">{{ editingProvider ? 'Edit Provider' : 'Add Provider' }}</h3>
            <button class="text-slate-500 hover:text-slate-300" @click="showProviderForm = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Name</label>
              <input v-model="providerForm.name" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Provider Type</label>
              <select v-model="providerForm.provider" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="openai_compatible">OpenAI Compatible</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">API Key{{ editingProvider ? ' (leave blank to keep)' : '' }}</label>
              <input v-model="providerForm.api_key" type="password" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Base URL</label>
              <input v-model="providerForm.base_url" placeholder="https://api.openai.com/v1" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-slate-400 mb-1">Models</label>
              <div class="flex flex-wrap items-center gap-1.5 min-h-[34px] w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 focus-within:border-blue-500">
                <span
                  v-for="(tag, idx) in providerModelTags"
                  :key="idx"
                  class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300"
                >
                  {{ tag }}
                  <button class="hover:text-blue-100" @click="removeProviderModelTag(idx)"><X class="w-3 h-3" /></button>
                </span>
                <input
                  v-model="providerModelInput"
                  placeholder="Type model name, press Enter"
                  class="flex-1 min-w-[140px] bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
                  @keydown="handleProviderModelKeydown"
                />
              </div>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Priority</label>
              <input v-model.number="providerForm.priority" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="flex items-center gap-2">
              <input v-model="providerForm.is_active" type="checkbox" class="rounded border-slate-600" />
              <label class="text-sm text-slate-300">Active</label>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" @click="showProviderForm = false">Cancel</Button>
            <Button variant="primary" size="sm" @click="saveProvider">{{ editingProvider ? 'Update' : 'Create' }}</Button>
          </div>
        </Card>

        <!-- Providers Table -->
        <Card :padding="false">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-slate-700/50">
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Name</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Type</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Base URL</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Models</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Priority</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Status</th>
                  <th class="text-right px-4 py-3 text-xs font-medium text-slate-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in providers" :key="p.id" class="border-b border-slate-700/30 hover:bg-slate-800/50">
                  <td class="px-4 py-3 text-slate-200 font-medium">{{ p.name }}</td>
                  <td class="px-4 py-3">
                    <span class="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">{{ p.provider }}</span>
                  </td>
                  <td class="px-4 py-3 text-slate-400 text-xs max-w-[200px] truncate">{{ p.base_url || '—' }}</td>
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-1.5">
                      <span v-if="p.models?.length" class="text-xs px-1.5 py-0.5 rounded-full bg-blue-900/30 text-blue-300 font-medium">{{ p.models.length }}</span>
                      <div class="flex flex-wrap gap-1">
                        <span v-for="m in (p.models ?? []).slice(0, 3)" :key="m" class="text-xs px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400">{{ m }}</span>
                        <span v-if="(p.models ?? []).length > 3" class="text-xs px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-500">+{{ p.models!.length - 3 }}</span>
                        <span v-if="!p.models?.length" class="text-xs text-slate-600">--</span>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-slate-400">{{ p.priority }}</td>
                  <td class="px-4 py-3">
                    <span :class="p.is_active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-slate-700 text-slate-400'" class="text-xs px-2 py-0.5 rounded-full">
                      {{ p.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <button class="text-slate-500 hover:text-blue-400 mr-2" @click="openProviderEdit(p)"><Pencil class="w-3.5 h-3.5" /></button>
                    <button
                      class="text-xs transition-colors"
                      :class="deleteConfirm[p.id] ? 'text-red-400 font-medium' : 'text-slate-500 hover:text-red-400'"
                      @click="requestDelete(p.id, handleDeleteProvider)"
                    >
                      <span v-if="deleteConfirm[p.id]">Confirm?</span>
                      <Trash2 v-else class="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
                <tr v-if="providers.length === 0">
                  <td colspan="7" class="px-4 py-12 text-center">
                    <div class="flex flex-col items-center text-slate-500">
                      <Server class="w-8 h-8 mb-2 text-slate-600" />
                      <p class="text-sm">No providers configured</p>
                      <p class="text-xs text-slate-600 mt-1">Add an AI provider to enable model access</p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <!-- Model Permissions Tab -->
      <div v-else-if="activeTab === 'models'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold text-white">Model Permissions</h2>
          <Button variant="primary" size="sm" @click="openPermCreate"><Plus class="w-4 h-4" /> New Permission</Button>
        </div>

        <!-- Permission Form -->
        <Card v-if="showPermForm" class="space-y-3">
          <div class="flex justify-between items-center mb-2">
            <h3 class="text-sm font-semibold text-slate-200">{{ editingPerm ? 'Edit Permission' : 'Add Permission' }}</h3>
            <button class="text-slate-500 hover:text-slate-300" @click="showPermForm = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Model</label>
              <input v-model="permForm.model" placeholder="gpt-4o" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">User Group</label>
              <select v-model="permForm.group_id" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none">
                <option value="">Select group</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.display_name }}</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Daily Limit</label>
              <input v-model.number="permForm.daily_limit" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Monthly Limit</label>
              <input v-model.number="permForm.monthly_limit" type="number" class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none" />
            </div>
            <div class="flex items-center gap-2">
              <input v-model="permForm.is_active" type="checkbox" class="rounded border-slate-600" />
              <label class="text-sm text-slate-300">Active</label>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" @click="showPermForm = false">Cancel</Button>
            <Button variant="primary" size="sm" @click="savePerm">{{ editingPerm ? 'Update' : 'Create' }}</Button>
          </div>
        </Card>

        <!-- Permissions Table -->
        <Card :padding="false">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-slate-700/50">
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Model</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Group</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Daily Limit</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Monthly Limit</th>
                  <th class="text-left px-4 py-3 text-xs font-medium text-slate-400 uppercase">Status</th>
                  <th class="text-right px-4 py-3 text-xs font-medium text-slate-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in modelPerms" :key="p.id" class="border-b border-slate-700/30 hover:bg-slate-800/50">
                  <td class="px-4 py-3">
                    <span class="text-xs px-2 py-0.5 rounded bg-blue-900/30 text-blue-300 font-mono">{{ p.model }}</span>
                  </td>
                  <td class="px-4 py-3 text-slate-300">{{ groupName(p.group_id) }}</td>
                  <td class="px-4 py-3 text-slate-400">{{ p.daily_limit === -1 ? 'Unlimited' : p.daily_limit }}</td>
                  <td class="px-4 py-3 text-slate-400">{{ p.monthly_limit === -1 ? 'Unlimited' : p.monthly_limit }}</td>
                  <td class="px-4 py-3">
                    <span :class="p.is_active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-slate-700 text-slate-400'" class="text-xs px-2 py-0.5 rounded-full">
                      {{ p.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <button class="text-slate-500 hover:text-blue-400 mr-2" @click="openPermEdit(p)"><Pencil class="w-3.5 h-3.5" /></button>
                    <button
                      class="text-xs transition-colors"
                      :class="deleteConfirm[p.id] ? 'text-red-400 font-medium' : 'text-slate-500 hover:text-red-400'"
                      @click="requestDelete(p.id, handleDeletePerm)"
                    >
                      <span v-if="deleteConfirm[p.id]">Confirm?</span>
                      <Trash2 v-else class="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
                <tr v-if="modelPerms.length === 0">
                  <td colspan="6" class="px-4 py-12 text-center">
                    <div class="flex flex-col items-center text-slate-500">
                      <Key class="w-8 h-8 mb-2 text-slate-600" />
                      <p class="text-sm">No model permissions configured</p>
                      <p class="text-xs text-slate-600 mt-1">Add permissions to control model access per group</p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
