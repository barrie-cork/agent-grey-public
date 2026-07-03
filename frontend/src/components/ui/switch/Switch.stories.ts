import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { Switch } from '.'
import { Label } from '../label'

const meta: Meta<typeof Switch> = {
  title: 'UI/Form/Switch',
  component: Switch,
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => ({
    components: { Switch },
    setup() {
      const checked = ref(false)
      return { checked }
    },
    template: '<Switch v-model:checked="checked" />',
  }),
}

export const WithLabel: Story = {
  render: () => ({
    components: { Switch, Label },
    setup() {
      const checked = ref(false)
      return { checked }
    },
    template: `
      <div class="flex items-center space-x-2">
        <Switch id="airplane-mode" v-model:checked="checked" />
        <Label for="airplane-mode">Airplane Mode</Label>
      </div>
    `,
  }),
}

export const Checked: Story = {
  render: () => ({
    components: { Switch, Label },
    setup() {
      const checked = ref(true)
      return { checked }
    },
    template: `
      <div class="flex items-center space-x-2">
        <Switch id="notifications" v-model:checked="checked" />
        <Label for="notifications">Enable notifications</Label>
      </div>
    `,
  }),
}

export const Disabled: Story = {
  render: () => ({
    components: { Switch, Label },
    template: `
      <div class="space-y-4">
        <div class="flex items-center space-x-2">
          <Switch id="disabled" disabled />
          <Label for="disabled" class="text-muted-foreground">Disabled</Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch id="disabled-on" disabled :checked="true" />
          <Label for="disabled-on" class="text-muted-foreground">Disabled (on)</Label>
        </div>
      </div>
    `,
  }),
}
