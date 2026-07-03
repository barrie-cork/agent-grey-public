<script setup lang="ts">
/**
 * ErrorAlert - Migrated to use Shadcn-vue Alert component
 *
 * This component maintains backward compatibility with the original API
 * while using the new Shadcn-vue Alert and Lucide icons.
 */
import { computed } from 'vue'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { AlertTriangle, AlertCircle, Info, X } from 'lucide-vue-next'

interface Props {
  variant?: 'error' | 'warning' | 'info'
  title: string
  message?: string
  dismissible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'error',
  dismissible: false
})

const emit = defineEmits<{
  dismiss: []
}>()

const alertVariant = computed(() => {
  if (props.variant === 'error') return 'destructive'
  return 'default'
})

const iconComponent = computed(() => {
  const iconMap = {
    error: AlertCircle,
    warning: AlertTriangle,
    info: Info
  }
  return iconMap[props.variant]
})

const iconColorClass = computed(() => {
  const colorMap = {
    error: 'text-destructive',
    warning: 'text-[color:var(--color-warning-dark)]',
    info: 'text-[color:var(--color-info-dark)]'
  }
  return colorMap[props.variant]
})

const alertBgClass = computed(() => {
  const bgMap = {
    error: '',
    warning: 'bg-[color:var(--color-warning-light)] border-[color:var(--color-warning)]',
    info: 'bg-[color:var(--color-info-light)] border-[color:var(--color-info)]'
  }
  return bgMap[props.variant]
})
</script>

<template>
  <Alert
    :variant="alertVariant"
    :class="alertBgClass"
    class="relative mb-4"
  >
    <component
      :is="iconComponent"
      :size="20"
      :class="iconColorClass"
      class="mt-0.5"
    />
    <div class="flex-1">
      <AlertTitle>{{ title }}</AlertTitle>
      <AlertDescription v-if="message" class="mt-1">
        {{ message }}
      </AlertDescription>
      <slot />
    </div>

    <Button
      v-if="dismissible"
      variant="ghost"
      size="icon"
      class="absolute top-2 right-2 h-6 w-6"
      aria-label="Dismiss"
      @click="emit('dismiss')"
    >
      <X :size="14" />
    </Button>
  </Alert>
</template>
