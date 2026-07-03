import { describe, it, expect } from 'vitest'
import { cn } from './utils'

describe('cn utility function', () => {
  it('merges class names correctly', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  it('deduplicates Tailwind classes with later values winning', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4')
  })

  it('handles conditional classes', () => {
    expect(cn('text-sm', false && 'text-lg')).toBe('text-sm')
    expect(cn('text-sm', true && 'text-lg')).toBe('text-lg')
  })

  it('handles undefined and null values', () => {
    expect(cn('px-2', undefined, null, 'py-1')).toBe('px-2 py-1')
  })

  it('handles empty inputs', () => {
    expect(cn()).toBe('')
  })

  it('handles conflicting Tailwind utility classes', () => {
    expect(cn('bg-red-500', 'bg-blue-500')).toBe('bg-blue-500')
  })

  it('handles array inputs', () => {
    expect(cn(['px-2', 'py-1'])).toBe('px-2 py-1')
  })

  it('handles object syntax', () => {
    expect(cn({ 'px-2': true, 'py-1': false })).toBe('px-2')
  })
})
