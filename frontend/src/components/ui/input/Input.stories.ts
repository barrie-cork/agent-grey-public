import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Input } from '.'
import { Label } from '../label'

const meta: Meta<typeof Input> = {
  title: 'UI/Form/Input',
  component: Input,
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'select',
      options: ['text', 'email', 'password', 'number', 'search', 'tel', 'url'],
    },
    placeholder: {
      control: 'text',
    },
    disabled: {
      control: 'boolean',
    },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    placeholder: 'Enter text...',
  },
}

export const WithLabel: Story = {
  render: () => ({
    components: { Input, Label },
    template: `
      <div class="grid w-full max-w-sm items-center gap-1.5">
        <Label for="email">Email</Label>
        <Input type="email" id="email" placeholder="Email" />
      </div>
    `,
  }),
}

export const Disabled: Story = {
  args: {
    disabled: true,
    placeholder: 'Disabled input',
  },
}

export const Password: Story = {
  args: {
    type: 'password',
    placeholder: 'Enter password',
  },
}

export const WithButton: Story = {
  render: () => ({
    components: { Input },
    template: `
      <div class="flex w-full max-w-sm items-center space-x-2">
        <Input type="email" placeholder="Email" />
        <button class="inline-flex items-center justify-center rounded-md text-sm font-medium bg-primary text-primary-foreground h-9 px-4 py-2">Subscribe</button>
      </div>
    `,
  }),
}

export const File: Story = {
  render: () => ({
    components: { Input, Label },
    template: `
      <div class="grid w-full max-w-sm items-center gap-1.5">
        <Label for="picture">Picture</Label>
        <Input id="picture" type="file" />
      </div>
    `,
  }),
}
