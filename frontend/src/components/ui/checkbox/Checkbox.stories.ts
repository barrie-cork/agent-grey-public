import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { Checkbox } from '.'
import { Label } from '../label'

const meta: Meta<typeof Checkbox> = {
  title: 'UI/Form/Checkbox',
  component: Checkbox,
  tags: ['autodocs'],
  argTypes: {
    disabled: {
      control: 'boolean',
    },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => ({
    components: { Checkbox },
    setup() {
      const checked = ref(false)
      return { checked }
    },
    template: '<Checkbox v-model:checked="checked" />',
  }),
}

export const WithLabel: Story = {
  render: () => ({
    components: { Checkbox, Label },
    setup() {
      const checked = ref(false)
      return { checked }
    },
    template: `
      <div class="flex items-center space-x-2">
        <Checkbox id="terms" v-model:checked="checked" />
        <Label for="terms">Accept terms and conditions</Label>
      </div>
    `,
  }),
}

export const Checked: Story = {
  render: () => ({
    components: { Checkbox, Label },
    setup() {
      const checked = ref(true)
      return { checked }
    },
    template: `
      <div class="flex items-center space-x-2">
        <Checkbox id="checked" v-model:checked="checked" />
        <Label for="checked">Checked by default</Label>
      </div>
    `,
  }),
}

export const Disabled: Story = {
  render: () => ({
    components: { Checkbox, Label },
    template: `
      <div class="space-y-4">
        <div class="flex items-center space-x-2">
          <Checkbox id="disabled" disabled />
          <Label for="disabled" class="text-muted-foreground">Disabled unchecked</Label>
        </div>
        <div class="flex items-center space-x-2">
          <Checkbox id="disabled-checked" disabled :checked="true" />
          <Label for="disabled-checked" class="text-muted-foreground">Disabled checked</Label>
        </div>
      </div>
    `,
  }),
}
