import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '.'
import { Button } from '../button'

const meta: Meta<typeof Card> = {
  title: 'UI/Card',
  component: Card,
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => ({
    components: { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter },
    template: `
      <Card class="w-[350px]">
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
          <CardDescription>Card description goes here.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>Card content with some example text to demonstrate the layout.</p>
        </CardContent>
        <CardFooter>
          <p class="text-sm text-muted-foreground">Card footer</p>
        </CardFooter>
      </Card>
    `,
  }),
}

export const WithForm: Story = {
  render: () => ({
    components: { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, Button },
    template: `
      <Card class="w-[350px]">
        <CardHeader>
          <CardTitle>Create project</CardTitle>
          <CardDescription>Deploy your new project in one-click.</CardDescription>
        </CardHeader>
        <CardContent>
          <form>
            <div class="grid w-full items-center gap-4">
              <div class="flex flex-col space-y-1.5">
                <label for="name" class="text-sm font-medium">Name</label>
                <input id="name" placeholder="Name of your project" class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm" />
              </div>
            </div>
          </form>
        </CardContent>
        <CardFooter class="flex justify-between">
          <Button variant="outline">Cancel</Button>
          <Button>Deploy</Button>
        </CardFooter>
      </Card>
    `,
  }),
}

export const Simple: Story = {
  render: () => ({
    components: { Card, CardContent },
    template: `
      <Card class="w-[350px]">
        <CardContent class="pt-6">
          <p>A simple card with just content, no header or footer.</p>
        </CardContent>
      </Card>
    `,
  }),
}

export const HeaderOnly: Story = {
  render: () => ({
    components: { Card, CardHeader, CardTitle, CardDescription },
    template: `
      <Card class="w-[350px]">
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>You have 3 unread messages.</CardDescription>
        </CardHeader>
      </Card>
    `,
  }),
}
