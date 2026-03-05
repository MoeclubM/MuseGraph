<script setup lang="ts">
import type { AdminUser, PaymentOrderListResponse, UserListResponse } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
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
  rowBalanceInput: Record<string, string>
  page: number
  pageSize: number
  expandedUserOrdersId: string | null
  userOrdersLoading: boolean
  userOrdersError: string
  userOrdersData: PaymentOrderListResponse | null
  statusChipClass: (value: string) => string
  orderStatusChipClass: (value: string) => string
  formatTokens: (value?: number) => string
  formatCurrency: (value?: number, digits?: number) => string
  formatDateTime: (value?: string | null) => string
  getUserTokenUsage: (user: AdminUser) => { totalTokens: number; requestCount: number; totalCost: number }
  getUserRechargeSummary: (user: AdminUser) => { totalOrders: number; paidOrders: number; paidAmount: number }
}>()

const emit = defineEmits<{
  'open-user-form': []
  'close-user-form': []
  'save-user': []
  'apply-user-filters': []
  'reset-user-filters': []
  'toggle-admin': [id: string, value: boolean]
  'add-balance-for-user': [id: string]
  'toggle-user-orders': [user: AdminUser]
  'load-user-orders': [userId: string]
  'remove-user': [id: string]
  'prev-page': []
  'next-page': []
}>()
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <div class="space-y-0.5">
        <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Users</h2>
        <p class="text-xs text-stone-500 dark:text-zinc-400">当前总数 {{ usersData?.total ?? 0 }}</p>
      </div>
      <Button size="sm" @click="emit('open-user-form')">New User</Button>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-3">
        <Input
          v-model="userFilters.search"
          placeholder="Search email / nickname"
          @keyup.enter="emit('apply-user-filters')"
        />
        <Select v-model="userFilters.is_admin">
          <option value="">All Roles</option>
          <option value="true">Admin</option>
          <option value="false">User</option>
        </Select>
        <Select v-model="userFilters.status">
          <option value="">All Status</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="DELETED">DELETED</option>
        </Select>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('reset-user-filters')">Reset</Button>
        <Button size="sm" @click="emit('apply-user-filters')">Search</Button>
      </div>
    </Card>

    <Card v-if="showUserForm" class="space-y-3">
      <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Create User</h3>
      <div class="grid gap-2 md:grid-cols-2">
        <Input v-model="userForm.email" placeholder="Email" />
        <Input v-model="userForm.nickname" placeholder="Nickname" />
        <Input v-model="userForm.password" type="password" placeholder="Password" />
        <Input v-model.number="userForm.balance" type="number" min="0" step="0.01" placeholder="Initial Balance" />
        <Select v-model="userForm.is_admin">
          <option :value="false">Normal User</option>
          <option :value="true">Administrator</option>
        </Select>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('close-user-form')">Cancel</Button>
        <Button size="sm" @click="emit('save-user')">Save</Button>
      </div>
    </Card>

    <Card :padding="false">
      <div class="py-3 sm:py-4">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
              <tr class="border-b border-stone-300 dark:border-zinc-700">
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Nickname</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Email</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Admin</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Status</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Balance</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Token Usage</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Recharge</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="u in usersData?.users ?? []" :key="u.id">
                <tr
                  class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                >
                  <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ u.nickname || '—' }}</td>
                  <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ u.email }}</td>
                  <td class="px-3 py-2">
                    <Button size="sm" variant="secondary" @click="emit('toggle-admin', u.id, !u.is_admin)">
                      {{ u.is_admin ? 'Remove Admin' : 'Make Admin' }}
                    </Button>
                  </td>
                  <td class="px-3 py-2">
                    <span :class="['inline-flex rounded-full border px-2 py-0.5 text-xs font-medium', statusChipClass(u.status)]">
                      {{ u.status }}
                    </span>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-stone-700 dark:text-zinc-200">{{ Number(u.balance).toFixed(2) }}</span>
                      <Input
                        v-model="rowBalanceInput[u.id]"
                        type="number"
                        step="0.01"
                        class="w-28"
                        placeholder="+金额"
                      />
                      <Button size="sm" variant="secondary" @click="emit('add-balance-for-user', u.id)">加余额</Button>
                    </div>
                  </td>
                  <td class="px-3 py-2">
                    <div class="space-y-0.5 text-xs">
                      <p class="text-stone-700 dark:text-zinc-200">{{ formatTokens(getUserTokenUsage(u).totalTokens) }} tokens</p>
                      <p class="text-stone-500 dark:text-zinc-400">{{ getUserTokenUsage(u).requestCount }} req · ${{ formatCurrency(getUserTokenUsage(u).totalCost) }}</p>
                    </div>
                  </td>
                  <td class="px-3 py-2">
                    <div class="space-y-0.5 text-xs">
                      <p class="text-stone-700 dark:text-zinc-200">{{ getUserRechargeSummary(u).totalOrders }} orders</p>
                      <p class="text-stone-500 dark:text-zinc-400">paid {{ getUserRechargeSummary(u).paidOrders }} · ${{ formatCurrency(getUserRechargeSummary(u).paidAmount, 2) }}</p>
                    </div>
                  </td>
                  <td class="px-3 py-2 text-right">
                    <div class="flex flex-wrap justify-end gap-2">
                      <Button size="sm" variant="secondary" @click="emit('toggle-user-orders', u)">
                        {{ expandedUserOrdersId === u.id ? 'Hide Orders' : 'View Orders' }}
                      </Button>
                      <Button size="sm" variant="danger" @click="emit('remove-user', u.id)">Delete</Button>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedUserOrdersId === u.id" class="border-b border-stone-200/80 bg-stone-100/40 dark:border-zinc-800 dark:bg-zinc-900/20">
                  <td colspan="8" class="px-3 py-3">
                    <div class="space-y-3">
                      <div class="flex items-center justify-between gap-2">
                        <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">充值订单 · {{ u.nickname || u.email }}</p>
                        <Button size="sm" variant="secondary" @click="emit('load-user-orders', u.id)">Refresh</Button>
                      </div>

                      <Alert v-if="userOrdersError" variant="destructive">{{ userOrdersError }}</Alert>

                      <div v-if="userOrdersLoading" class="text-xs text-stone-500 dark:text-zinc-400">
                        Loading orders...
                      </div>

                      <div v-else-if="userOrdersData?.orders?.length" class="overflow-x-auto">
                        <table class="w-full text-xs">
                          <thead class="bg-stone-200/60 dark:bg-zinc-800/70">
                            <tr class="border-b border-stone-300 dark:border-zinc-700">
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Order No</th>
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Amount</th>
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Status</th>
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Method</th>
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Created</th>
                              <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Paid</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr
                              v-for="order in userOrdersData.orders"
                              :key="order.id || order.order_no"
                              class="border-b border-stone-200/80 dark:border-zinc-800"
                            >
                              <td class="px-2 py-1.5 font-mono text-stone-700 dark:text-zinc-200">{{ order.order_no }}</td>
                              <td class="px-2 py-1.5 text-stone-700 dark:text-zinc-200">${{ formatCurrency(order.amount, 2) }}</td>
                              <td class="px-2 py-1.5">
                                <span :class="['inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium', orderStatusChipClass(order.status)]">
                                  {{ order.status }}
                                </span>
                              </td>
                              <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ order.payment_method || '—' }}</td>
                              <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.created_at) }}</td>
                              <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.paid_at) }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>

                      <p v-else class="text-xs text-stone-500 dark:text-zinc-400">No orders</p>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
      <div class="flex items-center justify-end gap-2 border-t border-stone-300/80 px-3 py-2 sm:px-4 dark:border-zinc-700/60">
        <Button size="sm" variant="secondary" :disabled="page <= 1" @click="emit('prev-page')">Prev</Button>
        <Button size="sm" variant="secondary" :disabled="!usersData || page * pageSize >= usersData.total" @click="emit('next-page')">Next</Button>
      </div>
    </Card>
  </div>
</template>
