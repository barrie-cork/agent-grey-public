import type { Preview } from '@storybook/vue3-vite'

// Import Tailwind CSS and design tokens
import '../src/assets/styles/main.css'

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      // 'todo' - show a11y violations in the test UI only
      // 'error' - fail CI on a11y violations
      // 'off' - skip a11y checks entirely
      test: 'todo',
    },
    backgrounds: {
      options: {
        light: { name: 'light', value: 'oklch(98.5% 0.002 247)' },
        dark: { name: 'dark', value: 'oklch(14.1% 0.005 286)' },
      },
      initial: 'light',
    },
    viewport: {
      options: {
        mobile: { name: 'Mobile', styles: { width: '375px', height: '667px' } },
        tablet: { name: 'Tablet', styles: { width: '768px', height: '1024px' } },
        desktop: { name: 'Desktop', styles: { width: '1280px', height: '800px' } },
      },
    },
  },
  decorators: [
    (story) => ({
      components: { story },
      template: '<div class="p-4 bg-background text-foreground"><story /></div>',
    }),
  ],
}

export default preview