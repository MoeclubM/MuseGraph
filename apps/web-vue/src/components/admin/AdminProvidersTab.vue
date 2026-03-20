<script setup lang="ts">
import type { Provider } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Checkbox from '@/components/ui/Checkbox.vue'

defineProps<{
  providers: Provider[]
  showProviderForm: boolean
  providerForm: {
    id: string
    name: string
    provider: string
    api_key: string
    base_url: string
    is_active: boolean
    priority: number
  }
  providerTypeOptions: string[]
}>()

const emit = defineEmits<{
  'new-provider': []
  'edit-provider': [provider: Provider]
  'close-provider-form': []
  'save-provider': []
  'remove-provider': [id: string]
}>()
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Providers</h2>
      <Button size="sm" @click="emit('new-provider')">New Provider</Button>
    </div>

    <Card v-if="showProviderForm" class="space-y-3">
      <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Provider Settings</h3>
      <div class="grid gap-2 md:grid-cols-2">
        <Input v-model="providerForm.name" placeholder="Name" />
        <div class="space-y-1">
          <Input
            v-model="providerForm.provider"
            list="provider-type-options"
            placeholder="Provider type"
          />
          <datalist id="provider-type-options">
            <option v-for="item in providerTypeOptions" :key="item" :value="item" />
          </datalist>
        </div>
        <Input v-model="providerForm.api_key" type="password" placeholder="API key" />
        <Input v-model="providerForm.base_url" placeholder="Base URL" />
        <Input v-model.number="providerForm.priority" type="number" placeholder="Priority" />
        <label class="inline-flex items-center gap-2 rounded-md border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Checkbox v-model="providerForm.is_active" />
          Active
        </label>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('close-provider-form')">Cancel</Button>
        <Button size="sm" @click="emit('save-provider')">Save</Button>
      </div>
    </Card>

    <Card :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
              <tr class="border-b border-stone-300 dark:border-zinc-700">
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Name</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Type</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Base URL</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="p in providers"
                :key="p.id"
                class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ p.name }}</td>
                <td class="px-3 py-2 font-mono text-xs text-stone-600 dark:text-zinc-300">{{ p.provider }}</td>
                <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ p.base_url || '—' }}</td>
                <td class="px-3 py-2 text-right">
                  <div class="flex flex-wrap justify-end gap-2">
                    <Button size="sm" variant="secondary" @click="emit('edit-provider', p)">Edit</Button>
                    <Button size="sm" variant="danger" @click="emit('remove-provider', p.id)">Delete</Button>
                  </div>
                </td>
              </tr>
            </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
