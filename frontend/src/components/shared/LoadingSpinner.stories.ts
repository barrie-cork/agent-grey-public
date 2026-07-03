import type { Meta, StoryObj } from '@storybook/vue3-vite'
import LoadingSpinner from './LoadingSpinner.vue'

const meta: Meta<typeof LoadingSpinner> = {
  title: 'Shared/LoadingSpinner',
  component: LoadingSpinner,
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'select',
      options: ['small', 'medium', 'large'],
    },
    text: { control: 'text' },
    fullPage: { control: 'boolean' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Small: Story = {
  args: { size: 'small' },
}

export const Large: Story = {
  args: { size: 'large' },
}

export const WithText: Story = {
  args: {
    text: 'Loading results...',
  },
}

export const FullPage: Story = {
  args: {
    fullPage: true,
    text: 'Loading...',
    size: 'large',
  },
}

export const AllSizes: Story = {
  render: () => ({
    components: { LoadingSpinner },
    template: `
      <div class="space-y-4">
        <div>
          <p class="text-sm font-medium mb-2">Small</p>
          <LoadingSpinner size="small" text="Loading..." />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Medium (default)</p>
          <LoadingSpinner size="medium" text="Loading..." />
        </div>
        <div>
          <p class="text-sm font-medium mb-2">Large</p>
          <LoadingSpinner size="large" text="Loading..." />
        </div>
      </div>
    `,
  }),
}
