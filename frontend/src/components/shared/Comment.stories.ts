import type { Meta, StoryObj } from '@storybook/vue3-vite'
import Comment from './Comment.vue'

// Mock data for stories
const mockAuthor = {
  id: '1',
  username: 'jsmith',
  first_name: 'John',
  last_name: 'Smith',
  email: 'john@example.com',
}

const mockComment = {
  id: '1',
  content: 'This is a **test comment** with some _markdown_ formatting.',
  author: mockAuthor,
  created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  is_edited: false,
  is_deleted: false,
  is_system_message: false,
  parent_comment: null,
  replies: [],
}

const meta: Meta<typeof Comment> = {
  title: 'Shared/Comment',
  component: Comment,
  tags: ['autodocs'],
  argTypes: {
    isReply: { control: 'boolean', description: 'Whether this is a nested reply' },
    canReply: { control: 'boolean', description: 'Whether reply button is shown' },
  },
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { comment: mockComment },
}

export const WithMarkdown: Story = {
  args: {
    comment: {
      ...mockComment,
      content: '## Heading\n\nThis has **bold**, *italic*, and a [link](https://example.com).\n\n- Bullet 1\n- Bullet 2',
    },
  },
}

export const SystemMessage: Story = {
  args: {
    comment: {
      ...mockComment,
      is_system_message: true,
      content: 'A re-vote has been proposed by John Smith.',
    },
  },
}

export const EditedComment: Story = {
  args: {
    comment: { ...mockComment, is_edited: true, content: 'This comment has been edited.' },
  },
}

export const DeletedComment: Story = {
  args: {
    comment: { ...mockComment, is_deleted: true },
  },
}

export const ReplyComment: Story = {
  args: { comment: mockComment, isReply: true },
}
