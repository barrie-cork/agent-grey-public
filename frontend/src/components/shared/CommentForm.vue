<template>
  <div class="bg-white rounded-lg border border-cool-grey-light p-4">
    <!-- Optional Criterion Tag Selector -->
    <div v-if="showCriterionTag" class="mb-3">
      <label for="criterion-tag" class="block text-xs font-medium text-cool-grey-dark mb-1">
        Tag a screening criterion (optional)
      </label>
      <select
        id="criterion-tag"
        v-model="selectedCriterionTag"
        class="w-full px-3 py-1.5 border border-cool-grey-light rounded-lg text-sm text-deep-navy bg-white focus:outline-none focus:ring-2 focus:ring-cta-blue focus:border-transparent transition-all duration-base"
      >
        <option value="">No criterion tag</option>
        <option value="relevance">Relevance to research question</option>
        <option value="grey_lit_classification">Grey literature classification</option>
        <option value="document_type">Document type appropriateness</option>
        <option value="population">Population match</option>
        <option value="intervention_interest">Intervention/interest match</option>
        <option value="context">Context appropriateness</option>
        <option value="full_text_availability">Full text availability</option>
        <option value="language">Language eligibility</option>
        <option value="other">Other criterion</option>
      </select>
    </div>

    <div class="mb-3">
      <label
        for="comment-content"
        class="block text-sm font-semibold text-deep-navy mb-2"
      >
        {{ label }}
        <span v-if="replyingTo" class="text-xs text-cool-grey font-normal ml-2">
          Replying to {{ replyingTo }}
        </span>
      </label>

      <!-- Tabs: Write / Preview -->
      <div class="flex items-center space-x-4 mb-2 border-b border-cool-grey-light">
        <button
          type="button"
          :class="tabClasses('write')"
          @click="activeTab = 'write'"
          aria-label="Write tab"
        >
          Write
        </button>
        <button
          type="button"
          :class="tabClasses('preview')"
          @click="activeTab = 'preview'"
          aria-label="Preview tab"
        >
          Preview
        </button>
      </div>

      <!-- Write Tab -->
      <textarea
        v-if="activeTab === 'write'"
        id="comment-content"
        data-testid="comment-textarea"
        ref="textareaRef"
        v-model="localContent"
        :placeholder="placeholder"
        :maxlength="maxLength"
        rows="4"
        class="w-full px-3 py-2 border border-cool-grey-light rounded-lg text-sm text-deep-navy placeholder-cool-grey focus:outline-none focus:ring-2 focus:ring-cta-blue focus:border-transparent resize-none transition-all duration-base"
        :aria-describedby="characterCountId"
        @input="autoResize"
      ></textarea>

      <!-- Preview Tab -->
      <div
        v-else
        class="min-h-[100px] px-3 py-2 border border-cool-grey-light rounded-lg prose prose-sm max-w-none bg-cool-grey-lighter"
      >
        <div v-if="localContent.trim()" v-html="sanitizedPreview"></div>
        <p v-else class="text-cool-grey italic">Nothing to preview</p>
      </div>
    </div>

    <!-- Character Count -->
    <div class="flex items-center justify-between mb-3">
      <span
        :id="characterCountId"
        :class="characterCountClasses"
      >
        {{ characterCount }} / {{ maxLength }}
      </span>

      <a
        href="https://www.markdownguide.org/basic-syntax/"
        target="_blank"
        rel="noopener noreferrer"
        class="text-xs text-cta-blue hover:text-cta-blue-dark transition-colors duration-base"
      >
        Markdown supported
      </a>
    </div>

    <!-- Action Buttons -->
    <div class="flex items-center justify-end space-x-3">
      <button
        v-if="showCancel"
        type="button"
        class="inline-flex items-center px-4 py-2 border border-cool-grey-light rounded-button text-sm font-medium text-deep-navy bg-white hover:bg-cool-grey-light focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-deep-navy transition-colors duration-base"
        @click="handleCancel"
      >
        Cancel
      </button>

      <button
        type="button"
        data-testid="post-comment-btn"
        :disabled="!isValid || isSubmitting"
        :class="submitButtonClasses"
        @click="handleSubmit"
        :aria-busy="isSubmitting"
      >
        <svg
          v-if="isSubmitting"
          class="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
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
        {{ submitButtonText }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

interface Props {
  label?: string
  placeholder?: string
  submitButtonText?: string
  maxLength?: number
  showCancel?: boolean
  isSubmitting?: boolean
  replyingTo?: string
  modelValue?: string
  showCriterionTag?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: 'Add your comment',
  placeholder: 'Write your comment here... (Markdown supported)',
  submitButtonText: 'Post Comment',
  maxLength: 5000,
  showCancel: false,
  isSubmitting: false,
  modelValue: '',
  showCriterionTag: false
})

const emit = defineEmits<{
  submit: [content: string, criterionTag?: string]
  cancel: []
  'update:modelValue': [value: string]
}>()

const localContent = ref(props.modelValue)
const activeTab = ref<'write' | 'preview'>('write')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const selectedCriterionTag = ref('')
const characterCountId = `character-count-${Math.random().toString(36).substring(7)}`

// Sync with v-model
watch(() => props.modelValue, (newValue) => {
  localContent.value = newValue
})

watch(localContent, (newValue) => {
  emit('update:modelValue', newValue)
})

const characterCount = computed(() => localContent.value.length)

const isValid = computed(() => {
  return localContent.value.trim().length > 0 && characterCount.value <= props.maxLength
})

const characterCountClasses = computed(() => {
  const base = 'text-xs'
  if (characterCount.value > props.maxLength * 0.9) {
    return `${base} text-alert-danger font-semibold`
  }
  if (characterCount.value > props.maxLength * 0.75) {
    return `${base} text-alert-warning`
  }
  return `${base} text-cool-grey`
})

const submitButtonClasses = computed(() => {
  const base = 'inline-flex items-center px-4 py-2 border border-transparent rounded-button text-sm font-medium transition-colors duration-base focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cta-blue'

  if (!isValid.value || props.isSubmitting) {
    return `${base} text-cool-grey bg-cool-grey-light cursor-not-allowed`
  }

  return `${base} text-white bg-cta-blue hover:bg-cta-blue-dark`
})

const tabClasses = (tab: 'write' | 'preview') => {
  const base = 'px-3 py-2 text-sm font-medium transition-colors duration-base focus:outline-none'
  const active = 'text-cta-blue border-b-2 border-cta-blue'
  const inactive = 'text-cool-grey hover:text-deep-navy'

  return `${base} ${activeTab.value === tab ? active : inactive}`
}

const sanitizedPreview = computed(() => {
  if (!localContent.value.trim()) return ''

  marked.setOptions({
    breaks: true,
    gfm: true
  })

  const html = marked.parse(localContent.value) as string

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
    ALLOWED_ATTR: ['href', 'target', 'rel']
  })
})

const autoResize = () => {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.height = `${textareaRef.value.scrollHeight}px`
    }
  })
}

const handleSubmit = () => {
  if (isValid.value && !props.isSubmitting) {
    emit('submit', localContent.value.trim(), selectedCriterionTag.value || undefined)
    selectedCriterionTag.value = ''
  }
}

const handleCancel = () => {
  localContent.value = ''
  activeTab.value = 'write'
  selectedCriterionTag.value = ''
  emit('cancel')
}

// Public method to reset the form
defineExpose({
  reset: () => {
    localContent.value = ''
    activeTab.value = 'write'
    selectedCriterionTag.value = ''
  }
})
</script>
