import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Textarea } from '.'
import { Label } from '../label'

const meta: Meta<typeof Textarea> = {
  title: 'UI/Form/Textarea',
  component: Textarea,
  tags: ['autodocs'],
  argTypes: {
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
    placeholder: 'Type your message here.',
  },
}

export const WithLabel: Story = {
  render: () => ({
    components: { Textarea, Label },
    template: `
      <div class="grid w-full gap-1.5">
        <Label for="message">Your message</Label>
        <Textarea placeholder="Type your message here." id="message" />
      </div>
    `,
  }),
}

export const WithText: Story = {
  render: () => ({
    components: { Textarea, Label },
    template: `
      <div class="grid w-full gap-1.5">
        <Label for="bio">Your bio</Label>
        <Textarea placeholder="Tell us a little bit about yourself" id="bio" />
        <p class="text-sm text-muted-foreground">
          Your bio will be displayed on your profile.
        </p>
      </div>
    `,
  }),
}

export const Disabled: Story = {
  args: {
    placeholder: 'Disabled textarea',
    disabled: true,
  },
}
