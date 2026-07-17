<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { AdminUser, UserListResponse } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'

type UserStatus = '' | 'ACTIVE' | 'SUSPENDED' | 'DELETED'
type UserAdminFilter = '' | 'true' | 'false'

interface UserFilters {
  search: string
  is_admin: UserAdminFilter
  status: UserStatus
}

interface UserForm {
  email: string
  password: string
  nickname: string
  is_admin: boolean
  balance: number
}

const props = defineProps<{
  usersData: UserListResponse | null
  showUserForm: boolean
  userFilters: UserFilters
  userForm: UserForm
  page: number
  pageSize: number
  statusChipClass: (value: string) => string
  formatTokens: (value?: number) => string
  formatCurrency: (value?: number, digits?: number) => string
  getUserTokenUsage: (user: AdminUser) => { totalTokens: number; requestCount: number; totalCost: number }
  getUserRechargeSummary: (user: AdminUser) => { totalOrders: number; paidOrders: number; paidAmount: number }
}>()

const emit = defineEmits<{
  'open-user-form': []
  'close-user-form': []
  'save-user': []
  'apply-user-filters': []
  'reset-user-filters': []
  'open-user-settings': [user: AdminUser]
  'remove-user': [id: string]
  'prev-page': []
  'next-page': []
}>()

const { t } = useI18n()
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <div class="space-y-0.5">
        <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">{{ t('admin.users.title') }}</h2>
        <p class="text-xs text-stone-500 dark:text-zinc-400">
          {{ t('admin.users.totalUsers', { count: usersData?.total ?? 0 }) }}
        </p>
      </div>
      <Button size="sm" @click="emit('open-user-form')">{{ t('admin.users.newUser') }}</Button>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-3">
        <Input
          v-model="userFilters.search"
          size="sm"
          :placeholder="t('admin.users.searchPlaceholder')"
          @keyup.enter="emit('apply-user-filters')"
        />
        <Select v-model="userFilters.is_admin" size="sm">
          <option value="">{{ t('admin.common.allRoles') }}</option>
          <option value="true">{{ t('admin.users.roleAdmin') }}</option>
          <option value="false">{{ t('admin.users.roleUser') }}</option>
        </Select>
        <Select v-model="userFilters.status" size="sm">
          <option value="">{{ t('admin.common.allStatus') }}</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="DELETED">DELETED</option>
        </Select>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('reset-user-filters')">{{ t('admin.common.reset') }}</Button>
        <Button size="sm" @click="emit('apply-user-filters')">{{ t('admin.common.search') }}</Button>
      </div>
    </Card>

    <Card v-if="showUserForm" class="space-y-3">
      <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">{{ t('admin.users.createUser') }}</h3>
      <div class="grid gap-2 md:grid-cols-2">
        <Input v-model="userForm.email" size="sm" placeholder="Email" />
        <Input v-model="userForm.nickname" size="sm" placeholder="Nickname" />
        <Input v-model="userForm.password" size="sm" type="password" placeholder="Password" />
        <Input v-model.number="userForm.balance" size="sm" type="number" min="0" step="0.01" :placeholder="t('admin.users.initialBalance')" />
        <Select v-model="userForm.is_admin" size="lg">
          <option :value="false">{{ t('admin.users.normalUser') }}</option>
          <option :value="true">{{ t('admin.users.administrator') }}</option>
        </Select>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('close-user-form')">{{ t('common.cancel') }}</Button>
        <Button size="sm" @click="emit('save-user')">{{ t('common.save') }}</Button>
      </div>
    </Card>

    <Card :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
            <tr class="border-b border-stone-300 dark:border-zinc-700">
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.common.name') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Email</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.users.adminColumn') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.status') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.users.balance') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.users.tokenUsage') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.users.recharge') }}</th>
              <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in usersData?.users ?? []"
              :key="u.id"
              class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
            >
              <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ u.nickname || '—' }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ u.email }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">
                {{ u.is_admin ? t('admin.users.roleAdmin') : t('admin.users.roleUser') }}
              </td>
              <td class="px-3 py-2">
                <span :class="['inline-flex rounded-full border px-2 py-0.5 text-xs font-medium', statusChipClass(u.status)]">
                  {{ u.status }}
                </span>
              </td>
              <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ Number(u.balance).toFixed(2) }}</td>
              <td class="px-3 py-2">
                <div class="space-y-0.5 text-xs">
                  <p class="text-stone-700 dark:text-zinc-200">{{ t('admin.common.tokensCount', { count: formatTokens(getUserTokenUsage(u).totalTokens) }) }}</p>
                  <p class="text-stone-500 dark:text-zinc-400">
                    {{ t('admin.common.reqCost', { requests: getUserTokenUsage(u).requestCount, cost: formatCurrency(getUserTokenUsage(u).totalCost) }) }}
                  </p>
                </div>
              </td>
              <td class="px-3 py-2">
                <div class="space-y-0.5 text-xs">
                  <p class="text-stone-700 dark:text-zinc-200">
                    {{ getUserRechargeSummary(u).totalOrders }} {{ t('admin.common.orders') }}
                  </p>
                  <p class="text-stone-500 dark:text-zinc-400">
                    {{ t('admin.common.paidSummary', { paid: getUserRechargeSummary(u).paidOrders, amount: formatCurrency(getUserRechargeSummary(u).paidAmount, 2) }) }}
                  </p>
                </div>
              </td>
              <td class="px-3 py-2 text-right">
                <div class="flex flex-wrap justify-end gap-2">
                  <Button size="sm" variant="secondary" @click="emit('open-user-settings', u)">
                    {{ t('admin.users.settings.open') }}
                  </Button>
                  <Button size="sm" variant="danger" @click="emit('remove-user', u.id)">{{ t('admin.common.delete') }}</Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="mt-4 flex items-center justify-end gap-2 border-t border-stone-300/80 pt-4 dark:border-zinc-700/60">
        <Button size="sm" variant="secondary" :disabled="page <= 1" @click="emit('prev-page')">{{ t('admin.common.prev') }}</Button>
        <Button size="sm" variant="secondary" :disabled="!usersData || page * pageSize >= usersData.total" @click="emit('next-page')">{{ t('admin.common.next') }}</Button>
      </div>
    </Card>
  </div>
</template>