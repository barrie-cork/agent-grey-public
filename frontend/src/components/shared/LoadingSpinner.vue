<template>
  <div :class="containerClasses">
    <svg
      :class="spinnerClasses"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      ></circle>
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      ></path>
    </svg>
    <span v-if="text" :class="textClasses">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * @deprecated Use LoadingState from '@/components/ui/loading-state' instead.
 * This component is kept for backward compatibility only.
 *
 * Migration:
 *   import { LoadingState } from '@/components/ui/loading-state'
 *   <LoadingState variant="spinner" />
 */
import { computed } from 'vue'

interface Props {
  size?: 'small' | 'medium' | 'large'
  text?: string
  fullPage?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium',
  fullPage: false
})

const containerClasses = computed(() => {
  const base = 'flex items-center justify-center'
  const spacing = props.fullPage ? 'p-8' : 'p-4'
  return `${base} ${spacing}`
})

const spinnerClasses = computed(() => {
  const sizeMap = {
    small: 'h-6 w-6',
    medium: 'h-8 w-8',
    large: 'h-12 w-12'
  }
  return `animate-spin ${sizeMap[props.size]} text-cta-blue`
})

const textClasses = computed(() => {
  const sizeMap = {
    small: 'text-xs',
    medium: 'text-sm',
    large: 'text-base'
  }
  return `ml-2 text-cool-grey ${sizeMap[props.size]}`
})
</script>
