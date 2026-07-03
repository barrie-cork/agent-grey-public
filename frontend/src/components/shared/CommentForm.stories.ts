import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import CommentForm from './CommentForm.vue'

const meta: Meta<typeof CommentForm> = {
  title: 'Shared/CommentForm',
  component: CommentForm,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    placeholder: { control: 'text' },
    submitButtonText: { control: 'text' },
    maxLength: { control: 'number' },
    showCancel: { control: 'boolean' },
    isSubmitting: { control: 'boolean' },
    replyingTo: { control: 'text' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => ({
    components: { CommentForm },
    setup() {
      return { args }
    },
    template: '<CommentForm v-bind="args" />',
  }),
}

export const WithReplyingTo: Story = {
  args: {
    replyingTo: 'John Smith',
    showCancel: true,
    label: 'Reply to comment',
  },
}

export const Submitting: Story = {
  args: {
    isSubmitting: true,
  },
}

export const CustomLabels: Story = {
  args: {
    label: 'Leave feedback',
    placeholder: 'Share your thoughts...',
    submitButtonText: 'Submit Feedback',
  },
}

export const Interactive: Story = {
  render: () => ({
    components: { CommentForm },
    setup() {
      const content = ref('')
      const isSubmitting = ref(false)
      const handleSubmit = (value: string) => {
        isSubmitting.value = true
        setTimeout(() => {
          alert(`Submitted: ${value}`)
          isSubmitting.value = false
          content.value = ''
        }, 1000)
      }
      return { content, isSubmitting, handleSubmit }
    },
    template: `
      <CommentForm
        v-model="content"
        :is-submitting="isSubmitting"
        @submit="handleSubmit"
      />
    `,
  }),
}
