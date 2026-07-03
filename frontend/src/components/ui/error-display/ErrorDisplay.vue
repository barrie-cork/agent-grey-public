<script setup lang="ts">
import { computed } from 'vue'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { AlertTriangle, X, RefreshCw } from 'lucide-vue-next'

interface Props {
  error: string | Error
  dismissible?: boolean
  retry?: boolean
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  dismissible: false,
  retry: false,
  title: 'Error'
})

const emit = defineEmits<{
  dismiss: []
  retry: []
}>()

const errorMessage = computed(() => {
  if (typeof props.error === 'string') {
    return props.error
  }
  if (props.error instanceof Error) {
    return props.error.message || props.error.toString()
  }
  try {
    return JSON.stringify(props.error)
  } catch {
    return String(props.error)
  }
})

const errorDetails = computed(() => {
  if (props.error instanceof Error && props.error.stack) {
    return props.error.stack
  }
  return null
})
</script>

<template>
  <Alert variant="destructive" class="relative">
    <AlertTriangle :size="16" class="mt-0.5" />
    <div class="flex-1">
      <AlertTitle>{{ title }}</AlertTitle>
      <AlertDescription class="mt-2">
        {{ errorMessage }}

        <details v-if="errorDetails" class="mt-2 text-xs">
          <summary class="cursor-pointer hover:underline">
            View stack trace
          </summary>
          <pre class="mt-2 overflow-x-auto bg-destructive/10 p-2 rounded text-xs">{{ errorDetails }}</pre>
        </details>
      </AlertDescription>

      <div
        v-if="retry"
        class="mt-3 flex gap-2"
      >
        <Button
          size="sm"
          variant="outline"
          @click="emit('retry')"
        >
          <RefreshCw :size="14" class="mr-1.5" />
          Retry
        </Button>
      </div>
    </div>

    <Button
      v-if="dismissible"
      variant="ghost"
      size="icon"
      class="absolute top-2 right-2 h-6 w-6"
      aria-label="Dismiss error"
      @click="emit('dismiss')"
    >
      <X :size="14" />
    </Button>
  </Alert>
</template>
