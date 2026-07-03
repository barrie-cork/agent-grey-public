import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { LoadingState } from '../loading-state'

describe('LoadingState', () => {
  it('renders spinner variant by default', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.find('svg').exists()).toBe(true) // Loader2 icon
    expect(wrapper.text()).toContain('Loading')
  })

  it('renders skeleton variant with default 3 lines', () => {
    const wrapper = mount(LoadingState, { props: { variant: 'skeleton' } })
    const skeletons = wrapper.findAll('[class*="animate-pulse"]')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)
  })

  it('renders skeleton variant with custom lines count', () => {
    const wrapper = mount(LoadingState, { props: { variant: 'skeleton', lines: 5 } })
    const skeletons = wrapper.findAll('[class*="animate-pulse"]')
    expect(skeletons.length).toBe(5)
  })

  it('renders card skeleton variant', () => {
    const wrapper = mount(LoadingState, { props: { variant: 'card' } })
    expect(wrapper.find('.border').exists()).toBe(true)
    expect(wrapper.findAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders table skeleton variant', () => {
    const wrapper = mount(LoadingState, { props: { variant: 'table' } })
    // Table header + 5 rows
    expect(wrapper.findAll('[class*="animate-pulse"]').length).toBeGreaterThanOrEqual(5)
  })

  it('has accessible role="status"', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
  })

  it('has aria-live="polite" for screen readers', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.find('[aria-live="polite"]').exists()).toBe(true)
  })

  it('has aria-label="Loading"', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.find('[aria-label="Loading"]').exists()).toBe(true)
  })

  it('spinner has animate-spin class', () => {
    const wrapper = mount(LoadingState, { props: { variant: 'spinner' } })
    expect(wrapper.find('.animate-spin').exists()).toBe(true)
  })
})
