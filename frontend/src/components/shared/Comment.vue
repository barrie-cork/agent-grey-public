<template>
  <div
    :class="commentContainerClasses"
    role="article"
    :aria-label="`Comment by ${authorName}`"
  >
    <div class="flex items-start space-x-3">
      <!-- Avatar -->
      <div v-if="!comment.is_system_message" class="flex-shrink-0">
        <div
          class="h-10 w-10 rounded-full bg-deep-navy flex items-center justify-center text-white font-semibold text-sm"
          :aria-label="`${authorName}'s avatar`"
        >
          {{ authorInitials }}
        </div>
      </div>

      <!-- System Message Icon -->
      <svg
        v-else
        class="w-5 h-5 text-info flex-shrink-0 mt-2"
        fill="currentColor"
        viewBox="0 0 20 20"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
          clip-rule="evenodd"
        />
      </svg>

      <!-- Comment Content -->
      <div class="flex-1 min-w-0">
        <!-- Header -->
        <div class="flex items-center justify-between mb-2">
          <div>
            <p class="text-sm font-semibold" :class="authorNameClass">
              {{ authorName }}
            </p>
            <p class="text-xs text-cool-grey">
              {{ relativeTime }}
              <span v-if="comment.is_edited" class="ml-1 italic">(edited)</span>
            </p>
          </div>

          <!-- Action Buttons -->
          <div v-if="!comment.is_system_message && canReply" class="flex items-center space-x-2">
            <button
              data-testid="reply-btn"
              class="text-xs text-cool-grey hover:text-deep-navy transition-colors duration-base focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cta-blue rounded px-2 py-1"
              @click="handleReply"
              :aria-label="`Reply to ${authorName}'s comment`"
            >
              Reply
            </button>
          </div>
        </div>

        <!-- Criterion Tag Badge -->
        <span
          v-if="comment.criterion_tag_display"
          class="inline-flex items-center text-xs bg-cool-grey-lighter text-cool-grey-dark rounded px-2 py-0.5 mb-2"
        >
          {{ comment.criterion_tag_display }}
        </span>

        <!-- Markdown Content -->
        <div
          v-if="!comment.is_deleted"
          data-testid="comment-content"
          class="prose prose-sm max-w-none text-cool-grey-dark"
          v-html="sanitizedContent"
        ></div>
        <div v-else class="text-sm text-cool-grey italic">
          [This comment has been deleted]
        </div>

        <!-- Straw Poll (if this comment initiated one) -->
        <VoteCard
          v-if="comment.discussion_vote"
          :vote="comment.discussion_vote"
          :current-user-id="currentUserId"
          :is-submitting="isSubmitting"
          @respond="(voteId, decision) => emit('voteRespond', voteId, decision)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { ConflictComment } from '@/types'
import VoteCard from './VoteCard.vue'

interface Props {
  comment: ConflictComment
  isReply?: boolean
  canReply?: boolean
  currentUserId?: string
  isSubmitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isReply: false,
  canReply: true,
  currentUserId: '',
  isSubmitting: false
})

const emit = defineEmits<{
  replyTo: [commentId: string]
  voteRespond: [voteId: string, decision: string]
}>()

const commentContainerClasses = computed(() => {
  const base = 'bg-white rounded-lg shadow-sm border p-4 mb-3'

  if (props.comment.is_system_message) {
    return `${base} bg-info-light border-l-4 border-info`
  }

  const indentation = props.isReply ? 'ml-comment-indent' : ''
  const borderColor = 'border-cool-grey-light'

  return `${base} ${borderColor} ${indentation}`.trim()
})

const authorName = computed(() => {
  if (props.comment.is_system_message) {
    return 'System Message'
  }

  const author = props.comment.author
  if (author.first_name || author.last_name) {
    return `${author.first_name} ${author.last_name}`.trim()
  }
  return author.username
})

const authorNameClass = computed(() => {
  return props.comment.is_system_message ? 'text-info-dark' : 'text-deep-navy'
})

const authorInitials = computed(() => {
  if (props.comment.is_system_message) return ''

  const author = props.comment.author
  const first = (author.first_name || author.username).charAt(0).toUpperCase()
  const last = (author.last_name || '').charAt(0).toUpperCase()
  return last ? `${first}${last}` : first
})

const relativeTime = computed(() => {
  const date = new Date(props.comment.created_at)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`

  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  })
})

const sanitizedContent = computed(() => {
  if (!props.comment.content) return ''

  // Configure marked for security
  marked.setOptions({
    breaks: true,
    gfm: true
  })

  // Convert markdown to HTML
  const html = marked.parse(props.comment.content) as string

  // Sanitise HTML with DOMPurify
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
    ALLOWED_ATTR: ['href', 'target', 'rel']
  })
})

const handleReply = () => {
  emit('replyTo', props.comment.id)
}
</script>
