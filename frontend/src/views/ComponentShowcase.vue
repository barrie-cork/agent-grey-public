<script setup lang="ts">
import { ref } from 'vue'

// Button
import { Button } from '@/components/ui/button'

// Card
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card'

// Alert
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

// Badge
import { Badge } from '@/components/ui/badge'

// Form components
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'

// Layout
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

// Feedback
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'

// Avatar
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'

const checked = ref(false)
const switched = ref(false)
const inputValue = ref('')
const textareaValue = ref('')
</script>

<template>
  <div class="max-w-7xl mx-auto p-8 space-y-12">
    <div>
      <h1 class="text-4xl font-bold text-foreground mb-2">Shadcn-vue Component Showcase</h1>
      <p class="text-muted-foreground">Phase 03: Component Library Installation - 103 components installed</p>
    </div>

    <Separator />

    <!-- Buttons -->
    <Card>
      <CardHeader>
        <CardTitle>Buttons</CardTitle>
        <CardDescription>Button component with all variants</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-4">
        <Button>Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Destructive</Button>
        <Button variant="link">Link</Button>
        <Button disabled>Disabled</Button>
      </CardContent>
      <CardFooter>
        <p class="text-sm text-muted-foreground">7 button variants demonstrated</p>
      </CardFooter>
    </Card>

    <!-- Alerts -->
    <Card>
      <CardHeader>
        <CardTitle>Alerts</CardTitle>
        <CardDescription>Alert component with variants</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <Alert>
          <AlertTitle>Default Alert</AlertTitle>
          <AlertDescription>This is a default alert message for general information.</AlertDescription>
        </Alert>
        <Alert variant="destructive">
          <AlertTitle>Error Alert</AlertTitle>
          <AlertDescription>This is a destructive alert for error states.</AlertDescription>
        </Alert>
      </CardContent>
    </Card>

    <!-- Badges -->
    <Card>
      <CardHeader>
        <CardTitle>Badges</CardTitle>
        <CardDescription>Badge component with variants</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-4">
        <Badge>Default</Badge>
        <Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge>
        <Badge variant="destructive">Destructive</Badge>
      </CardContent>
    </Card>

    <!-- Form Inputs -->
    <Card>
      <CardHeader>
        <CardTitle>Form Inputs</CardTitle>
        <CardDescription>Input, textarea, checkbox, and switch components</CardDescription>
      </CardHeader>
      <CardContent class="space-y-6">
        <div class="space-y-2">
          <Label for="email">Email</Label>
          <Input id="email" v-model="inputValue" type="email" placeholder="Enter your email" />
        </div>

        <div class="space-y-2">
          <Label for="message">Message</Label>
          <Textarea id="message" v-model="textareaValue" placeholder="Enter your message" />
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox id="terms" v-model:checked="checked" />
          <Label for="terms">Accept terms and conditions</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Switch id="notifications" v-model:checked="switched" />
          <Label for="notifications">Enable notifications</Label>
        </div>
      </CardContent>
    </Card>

    <!-- Tabs -->
    <Card>
      <CardHeader>
        <CardTitle>Tabs</CardTitle>
        <CardDescription>Tabs component for navigation</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs default-value="overview" class="w-full">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" class="p-4">
            <p>Overview content goes here.</p>
          </TabsContent>
          <TabsContent value="analytics" class="p-4">
            <p>Analytics content goes here.</p>
          </TabsContent>
          <TabsContent value="settings" class="p-4">
            <p>Settings content goes here.</p>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>

    <!-- Loading States -->
    <Card>
      <CardHeader>
        <CardTitle>Loading States</CardTitle>
        <CardDescription>Progress and skeleton components</CardDescription>
      </CardHeader>
      <CardContent class="space-y-6">
        <div class="space-y-2">
          <p class="text-sm">Progress: 66%</p>
          <Progress :model-value="66" />
        </div>

        <div class="space-y-2">
          <p class="text-sm text-muted-foreground">Loading skeleton:</p>
          <div class="flex items-center space-x-4">
            <Skeleton class="h-12 w-12 rounded-full" />
            <div class="space-y-2">
              <Skeleton class="h-4 w-[250px]" />
              <Skeleton class="h-4 w-[200px]" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Avatar -->
    <Card>
      <CardHeader>
        <CardTitle>Avatar</CardTitle>
        <CardDescription>Avatar component with image and fallback</CardDescription>
      </CardHeader>
      <CardContent class="flex gap-4">
        <Avatar>
          <AvatarImage src="https://github.com/shadcn.png" alt="@shadcn" />
          <AvatarFallback>CN</AvatarFallback>
        </Avatar>
        <Avatar>
          <AvatarFallback>JD</AvatarFallback>
        </Avatar>
        <Avatar>
          <AvatarFallback>AG</AvatarFallback>
        </Avatar>
      </CardContent>
    </Card>

    <!-- Semantic Tokens Test -->
    <Card>
      <CardHeader>
        <CardTitle>Semantic Tokens (Phase 02)</CardTitle>
        <CardDescription>Verifying design tokens work with components</CardDescription>
      </CardHeader>
      <CardContent class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="space-y-2">
          <div class="h-16 bg-primary rounded-lg" />
          <p class="text-sm text-center">Primary</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 bg-secondary rounded-lg" />
          <p class="text-sm text-center">Secondary</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 bg-accent rounded-lg" />
          <p class="text-sm text-center">Accent</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 bg-muted rounded-lg" />
          <p class="text-sm text-center">Muted</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 bg-destructive rounded-lg" />
          <p class="text-sm text-center">Destructive</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 border-2 border-border rounded-lg" />
          <p class="text-sm text-center">Border</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 bg-input rounded-lg" />
          <p class="text-sm text-center">Input</p>
        </div>
        <div class="space-y-2">
          <div class="h-16 ring-2 ring-ring rounded-lg" />
          <p class="text-sm text-center">Ring</p>
        </div>
      </CardContent>
    </Card>

    <!-- Component Summary -->
    <Card>
      <CardHeader>
        <CardTitle>Installation Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <ul class="list-disc list-inside space-y-1 text-sm">
          <li>25 base components installed</li>
          <li>103 Vue component files total</li>
          <li>All TypeScript types verified</li>
          <li>Components use Phase 02 OKLCH tokens</li>
          <li>Reka UI primitives for accessibility</li>
        </ul>
      </CardContent>
    </Card>
  </div>
</template>
