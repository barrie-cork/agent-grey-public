<template>
  <div class="space-y-4">
    <!-- Thread Header -->
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-deep-navy">
        Discussion Thread
        <span class="text-cool-grey font-normal text-sm ml-2">({{ totalComments }} comment{{ totalComments !== 1 ? 's' : '' }})</span>
      </h3>
    </div>

    <!-- Empty State -->
    <div
      v-if="topLevelComments.length === 0"
      class="bg-cool-grey-lighter border border-cool-grey-light rounded-lg p-8 text-center"
    >
      <svg
        class="mx-auto h-12 w-12 text-cool-grey mb-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
      <p class="text-cool-grey text-sm">
        No comments yet. Be the first to start the discussion!
      </p>
    </div>

    <!-- Comment List -->
    <div v-else class="space-y-4">
      <div
        v-for="comment in topLevelComments"
        :key="comment.id"
      >
        <!-- Top-level Comment -->
        <Comment
          :comment="comment"
          :can-reply="canComment"
          :current-user-id="currentUserId"
          :is-submitting="isSubmitting"
          @reply-to="handleReplyTo"
          @vote-respond="(voteId, decision) => emit('voteRespond', voteId, decision)"
        />

        <!-- Nested Replies -->
        <div v-if="comment.replies && comment.replies.length > 0" class="space-y-3">
          <Comment
            v-for="reply in comment.replies"
            :key="reply.id"
            :comment="reply"
            :is-reply="true"
            :can-reply="canComment"
            :current-user-id="currentUserId"
            :is-submitting="isSubmitting"
            @reply-to="handleReplyTo"
            @vote-respond="(voteId, decision) => emit('voteRespond', voteId, decision)"
          />
        </div>
      </div>
    </div>

    <!-- Comment Form -->
    <div v-if="canComment" class="mt-6">
      <CommentForm
        ref="commentFormRef"
        :label="formLabel"
        :replying-to="replyingToName"
        :is-submitting="isSubmitting"
        :show-cancel="!!replyingToId"
        :show-criterion-tag="showCriterionTag"
        v-model="commentContent"
        @submit="handleSubmitComment"
        @cancel="handleCancelReply"
      />
    </div>

    <!-- Discussion Actions -->
    <div v-if="canComment && topLevelComments.length > 0" class="mt-6 pt-4 border-t border-cool-grey-light flex flex-wrap gap-3">
      <Button
        variant="outline"
        size="sm"
        class="text-xs font-semibold"
        @click="$emit('proposeStrawPoll')"
      >
        <BarChart3 class="h-3.5 w-3.5 mr-1.5" />
        Propose Straw Poll
      </Button>

      <Button
        v-if="canProposeRevote && !hasActiveRevoteProposal"
        variant="outline"
        size="sm"
        class="text-xs font-semibold text-destructive border-destructive/30 hover:bg-destructive/5 hover:text-destructive"
        @click="$emit('proposeRevote')"
      >
        <RotateCcw class="h-3.5 w-3.5 mr-1.5" />
        Suggest Fresh Assessment
      </Button>
    </div>
    <div v-else-if="canProposeRevote && !hasActiveRevoteProposal" class="mt-6 pt-4 border-t border-cool-grey-light">
      <Button
        variant="outline"
        size="sm"
        class="text-xs font-semibold text-destructive border-destructive/30 hover:bg-destructive/5 hover:text-destructive"
        @click="$emit('proposeRevote')"
      >
        <RotateCcw class="h-3.5 w-3.5 mr-1.5" />
        Suggest Fresh Assessment
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { BarChart3, RotateCcw } from 'lucide-vue-next'
import type { ConflictComment } from '@/types'
import { Button } from '@/components/ui/button'
import Comment from './Comment.vue'
import CommentForm from './CommentForm.vue'

interface Props {
  comments: ConflictComment[]
  canComment?: boolean
  canProposeRevote?: boolean
  hasActiveRevoteProposal?: boolean
  isSubmitting?: boolean
  currentUserId?: string
  showCriterionTag?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canComment: true,
  canProposeRevote: false,
  hasActiveRevoteProposal: false,
  isSubmitting: false,
  currentUserId: '',
  showCriterionTag: false
})

const emit = defineEmits<{
  postComment: [content: string, parentId?: string, criterionTag?: string]
  proposeRevote: []
  proposeStrawPoll: []
  voteRespond: [voteId: string, decision: string]
}>()

const commentContent = ref('')
const replyingToId = ref<string | null>(null)
const commentFormRef = ref<InstanceType<typeof CommentForm> | null>(null)

const topLevelComments = computed(() => {
  // Filter out replies and return only top-level comments
  // Replies are included in the parent comment's 'replies' array
  return props.comments.filter(comment => !comment.parent_comment)
})

const totalComments = computed(() => {
  // Count all comments including replies
  let count = 0
  const countComments = (comments: ConflictComment[]) => {
    comments.forEach(comment => {
      count++
      if (comment.replies && comment.replies.length > 0) {
        countComments(comment.replies)
      }
    })
  }
  countComments(topLevelComments.value)
  return count
})

const replyingToName = computed(() => {
  if (!replyingToId.value) return undefined

  // Find the comment we're replying to
  const findComment = (comments: ConflictComment[]): ConflictComment | undefined => {
    for (const comment of comments) {
      if (comment.id === replyingToId.value) return comment
      if (comment.replies && comment.replies.length > 0) {
        const found = findComment(comment.replies)
        if (found) return found
      }
    }
    return undefined
  }

  const comment = findComment(props.comments)
  if (!comment) return undefined

  const author = comment.author
  if (author.first_name || author.last_name) {
    return `${author.first_name} ${author.last_name}`.trim()
  }
  return author.username
})

const formLabel = computed(() => {
  return replyingToId.value ? 'Reply to comment' : 'Add your comment'
})

const handleReplyTo = (commentId: string) => {
  replyingToId.value = commentId
  // Scroll to comment form
  setTimeout(() => {
    commentFormRef.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, 100)
}

const handleSubmitComment = (content: string, criterionTag?: string) => {
  emit('postComment', content, replyingToId.value || undefined, criterionTag)

  // Reset form after successful submission
  if (commentFormRef.value) {
    commentFormRef.value.reset()
  }
  replyingToId.value = null
}

const handleCancelReply = () => {
  replyingToId.value = null
  if (commentFormRef.value) {
    commentFormRef.value.reset()
  }
}
</script>
