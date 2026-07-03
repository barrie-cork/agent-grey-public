<template>
  <Dialog :open="open" @update:open="handleOpenChange">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle class="text-deep-navy">{{ title }}</DialogTitle>
        <DialogDescription v-if="description">{{ description }}</DialogDescription>
      </DialogHeader>

      <div class="py-2">
        <Textarea
          ref="textareaRef"
          v-model="text"
          :placeholder="placeholder"
          class="min-h-[100px] border-scholar focus:border-deep-navy"
        />
      </div>

      <DialogFooter class="gap-2 sm:gap-0">
        <Button
          variant="outline"
          @click="handleCancel"
        >
          Cancel
        </Button>
        <Button
          :disabled="required && !text.trim()"
          class="bg-deep-navy hover:bg-deep-navy-dark text-white"
          @click="handleConfirm"
        >
          {{ submitLabel }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface Props {
  open: boolean
  title: string
  description?: string
  placeholder?: string
  required?: boolean
  submitLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  placeholder: '',
  required: false,
  submitLabel: 'Submit',
})

const emit = defineEmits<{
  confirm: [text: string]
  cancel: []
}>()

const text = ref('')
const textareaRef = ref<InstanceType<typeof Textarea> | null>(null)

// Reset text when dialog opens
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    text.value = ''
  }
})

function handleConfirm() {
  emit('confirm', text.value.trim())
  text.value = ''
}

function handleCancel() {
  emit('cancel')
  text.value = ''
}

function handleOpenChange(value: boolean) {
  if (!value) {
    handleCancel()
  }
}
</script>
