import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { ErrorDisplay } from '../error-display'

describe('ErrorDisplay', () => {
  it('renders error message from string', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Something went wrong' }
    })
    expect(wrapper.text()).toContain('Something went wrong')
  })

  it('renders error message from Error object', () => {
    const error = new Error('Test error message')
    const wrapper = mount(ErrorDisplay, { props: { error } })
    expect(wrapper.text()).toContain('Test error message')
  })

  it('renders default title "Error"', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error' }
    })
    expect(wrapper.text()).toContain('Error')
  })

  it('renders custom title', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error', title: 'Custom Title' }
    })
    expect(wrapper.text()).toContain('Custom Title')
  })

  it('shows dismiss button when dismissible is true', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error', dismissible: true }
    })
    expect(wrapper.find('[aria-label="Dismiss error"]').exists()).toBe(true)
  })

  it('hides dismiss button by default', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error' }
    })
    expect(wrapper.find('[aria-label="Dismiss error"]').exists()).toBe(false)
  })

  it('emits dismiss event when dismiss button clicked', async () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error', dismissible: true }
    })
    await wrapper.find('[aria-label="Dismiss error"]').trigger('click')
    expect(wrapper.emitted('dismiss')).toBeTruthy()
  })

  it('shows retry button when retry is true', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error', retry: true }
    })
    expect(wrapper.text()).toContain('Retry')
  })

  it('hides retry button by default', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error' }
    })
    expect(wrapper.text()).not.toContain('Retry')
  })

  it('emits retry event when retry button clicked', async () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error', retry: true }
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })

  it('shows stack trace details for Error objects', () => {
    const error = new Error('Test error')
    error.stack = 'Error: Test error\n    at test.ts:1:1'
    const wrapper = mount(ErrorDisplay, { props: { error } })
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.text()).toContain('View stack trace')
  })

  it('renders AlertTriangle icon', () => {
    const wrapper = mount(ErrorDisplay, {
      props: { error: 'Test error' }
    })
    expect(wrapper.find('svg').exists()).toBe(true)
  })
})
