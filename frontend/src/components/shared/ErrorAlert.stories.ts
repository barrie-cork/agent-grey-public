import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import ErrorAlert from './ErrorAlert.vue'

const meta: Meta<typeof ErrorAlert> = {
  title: 'Shared/ErrorAlert',
  component: ErrorAlert,
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['error', 'warning', 'info'],
    },
    title: { control: 'text' },
    message: { control: 'text' },
    dismissible: { control: 'boolean' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Error: Story = {
  args: {
    variant: 'error',
    title: 'Error',
    message: 'Something went wrong. Please try again later.',
  },
}

export const Warning: Story = {
  args: {
    variant: 'warning',
    title: 'Warning',
    message: 'Your session will expire in 5 minutes.',
  },
}

export const Info: Story = {
  args: {
    variant: 'info',
    title: 'Information',
    message: 'New features are available. Check the changelog for details.',
  },
}

export const Dismissible: Story = {
  render: () => ({
    components: { ErrorAlert },
    setup() {
      const visible = ref(true)
      const handleDismiss = () => {
        visible.value = false
      }
      const reset = () => {
        visible.value = true
      }
      return { visible, handleDismiss, reset }
    },
    template: `
      <div>
        <ErrorAlert
          v-if="visible"
          variant="warning"
          title="Dismissible Alert"
          message="Click the X button to dismiss this alert."
          dismissible
          @dismiss="handleDismiss"
        />
        <button
          v-else
          @click="reset"
          class="px-4 py-2 bg-primary text-primary-foreground rounded"
        >
          Show Alert Again
        </button>
      </div>
    `,
  }),
}

export const TitleOnly: Story = {
  args: {
    variant: 'error',
    title: 'Connection Lost',
  },
}

export const AllVariants: Story = {
  render: () => ({
    components: { ErrorAlert },
    template: `
      <div class="space-y-4">
        <ErrorAlert
          variant="error"
          title="Error"
          message="An error occurred while processing your request."
        />
        <ErrorAlert
          variant="warning"
          title="Warning"
          message="Please save your work before the session expires."
        />
        <ErrorAlert
          variant="info"
          title="Information"
          message="Your profile has been updated successfully."
        />
      </div>
    `,
  }),
}
