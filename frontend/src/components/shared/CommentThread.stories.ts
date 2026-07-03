import type { Meta, StoryObj } from '@storybook/vue3-vite'
import CommentThread from './CommentThread.vue'

const mockAuthor1 = {
  id: '1',
  username: 'jsmith',
  first_name: 'John',
  last_name: 'Smith',
  email: 'john@example.com',
}

const mockAuthor2 = {
  id: '2',
  username: 'mjones',
  first_name: 'Mary',
  last_name: 'Jones',
  email: 'mary@example.com',
}

const mockComments = [
  {
    id: '1',
    content: 'I think this result should be included because it directly addresses our research question.',
    author: mockAuthor1,
    created_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
    is_edited: false,
    is_deleted: false,
    is_system_message: false,
    parent_comment: null,
    replies: [
      {
        id: '2',
        content: 'I agree, the methodology section is particularly relevant.',
        author: mockAuthor2,
        created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
        is_edited: false,
        is_deleted: false,
        is_system_message: false,
        parent_comment: '1',
        replies: [],
      },
    ],
  },
  {
    id: '3',
    content: 'However, I noticed the sample size is quite small. Should we flag this?',
    author: mockAuthor2,
    created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    is_edited: false,
    is_deleted: false,
    is_system_message: false,
    parent_comment: null,
    replies: [],
  },
]

const meta: Meta<typeof CommentThread> = {
  title: 'Shared/CommentThread',
  component: CommentThread,
  tags: ['autodocs'],
  argTypes: {
    canComment: { control: 'boolean' },
    canProposeRevote: { control: 'boolean' },
    hasActiveRevoteProposal: { control: 'boolean' },
    isSubmitting: { control: 'boolean' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    comments: mockComments,
  },
}

export const Empty: Story = {
  args: {
    comments: [],
  },
}

export const WithRevoteButton: Story = {
  args: {
    comments: mockComments,
    canProposeRevote: true,
  },
}

export const RevoteAlreadyProposed: Story = {
  args: {
    comments: [
      ...mockComments,
      {
        id: '4',
        content: 'A re-vote has been proposed.',
        author: mockAuthor1,
        created_at: new Date().toISOString(),
        is_edited: false,
        is_deleted: false,
        is_system_message: true,
        parent_comment: null,
        replies: [],
      },
    ],
    canProposeRevote: true,
    hasActiveRevoteProposal: true,
  },
}

export const ReadOnly: Story = {
  args: {
    comments: mockComments,
    canComment: false,
  },
}

export const Submitting: Story = {
  args: {
    comments: mockComments,
    isSubmitting: true,
  },
}
