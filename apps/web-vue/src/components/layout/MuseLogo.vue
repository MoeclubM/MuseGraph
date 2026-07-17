<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: 'sm' | 'md' | 'lg'
  }>(),
  {
    size: 'md',
  },
)

const sizeMap = {
  sm: { container: 'h-8 w-8', svg: 32 },
  md: { container: 'h-12 w-12', svg: 48 },
  lg: { container: 'h-16 w-16', svg: 64 },
}
</script>

<template>
  <div
    :class="[
      'mx-auto flex items-center justify-center rounded-xl bg-[color:var(--muse-accent)] shadow-sm',
      sizeMap[size].container,
    ]"
  >
    <svg
      :width="sizeMap[size].svg * 0.52"
      :height="sizeMap[size].svg * 0.52"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M4 18.5V6.5L12 14L20 6.5V18.5"
        stroke="var(--muse-accent-ink)"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M17.5 4.5C18.3284 4.5 19 5.17157 19 6C19 6.82843 18.3284 7.5 17.5 7.5"
        stroke="var(--muse-accent-ink)"
        stroke-width="1.6"
        stroke-linecap="round"
        opacity="0.6"
      />
    </svg>
  </div>
</template>
