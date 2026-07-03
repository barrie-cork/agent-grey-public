/**
 * useMarkdown Composable
 * Safe markdown rendering with DOMPurify sanitization
 *
 * Phase 7: Pinia Store & Composables
 *
 * Features:
 * - Convert markdown to HTML using marked library
 * - Sanitize output with DOMPurify (XSS prevention)
 * - Support basic markdown: bold, italic, lists, links, code blocks
 * - Configure allowed HTML tags and attributes
 *
 * Usage:
 * ```typescript
 * import { useMarkdown } from '@/composables/useMarkdown'
 *
 * const { renderMarkdown } = useMarkdown()
 * const safeHtml = renderMarkdown('**Bold** and _italic_ text')
 * ```
 */

import { marked } from 'marked';
import DOMPurify from 'dompurify';

/**
 * DOMPurify configuration for markdown sanitization
 * Allows safe HTML tags for formatted text
 */
const PURIFY_CONFIG = {
  ALLOWED_TAGS: [
    // Text formatting
    'p', 'br', 'strong', 'em', 'u', 's', 'code', 'pre',
    // Headings
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    // Lists
    'ul', 'ol', 'li',
    // Links
    'a',
    // Block elements
    'blockquote', 'hr',
    // Code blocks
    'div', 'span',
  ],
  ALLOWED_ATTR: [
    'href', 'target', 'rel', 'class',
  ],
  // Force all links to open in new tab with security attributes
  ALLOW_DATA_ATTR: false,
  ALLOW_UNKNOWN_PROTOCOLS: false,
  SAFE_FOR_TEMPLATES: true,
};

/**
 * Marked configuration for markdown parsing
 */
marked.setOptions({
  // GitHub Flavored Markdown
  gfm: true,
  breaks: true, // Convert \n to <br>
});

export function useMarkdown() {
  /**
   * Render markdown to sanitized HTML
   *
   * @param content - Markdown string
   * @returns Safe HTML string
   *
   * Example:
   * ```typescript
   * const html = renderMarkdown('**Bold** and [link](https://example.com)')
   * // Returns: '<p><strong>Bold</strong> and <a href="https://example.com" target="_blank" rel="noopener noreferrer">link</a></p>'
   * ```
   */
  function renderMarkdown(content: string): string {
    if (!content || content.trim() === '') {
      return '';
    }

    try {
      // Step 1: Convert markdown to HTML
      const rawHtml = marked.parse(content) as string;

      // Step 2: Sanitize HTML with DOMPurify
      const cleanHtml = DOMPurify.sanitize(rawHtml, PURIFY_CONFIG);

      // Step 3: Add security attributes to all links
      const secureHtml = addLinkSecurity(cleanHtml);

      return secureHtml;
    } catch (err) {
      console.error('Markdown rendering error:', err);
      // Return escaped plain text on error
      return escapeHtml(content);
    }
  }

  /**
   * Add security attributes to all links
   * Ensures all <a> tags have target="_blank" and rel="noopener noreferrer"
   *
   * @param html - HTML string
   * @returns HTML with secure link attributes
   */
  function addLinkSecurity(html: string): string {
    // Create temporary DOM element
    const div = document.createElement('div');
    div.innerHTML = html;

    // Find all links and add security attributes
    const links = div.querySelectorAll('a');
    links.forEach((link) => {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    });

    return div.innerHTML;
  }

  /**
   * Escape HTML special characters
   * Fallback for rendering errors
   *
   * @param text - Plain text
   * @returns Escaped HTML string
   */
  function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Strip HTML tags from rendered markdown
   * Useful for previews and meta descriptions
   *
   * @param content - Markdown string
   * @returns Plain text without HTML
   *
   * Example:
   * ```typescript
   * const plain = stripMarkdown('**Bold** text')
   * // Returns: 'Bold text'
   * ```
   */
  function stripMarkdown(content: string): string {
    if (!content || content.trim() === '') {
      return '';
    }

    try {
      // Render markdown
      const html = renderMarkdown(content);

      // Strip HTML tags
      const div = document.createElement('div');
      div.innerHTML = html;
      return div.textContent || div.innerText || '';
    } catch (err) {
      console.error('Markdown stripping error:', err);
      return content;
    }
  }

  /**
   * Truncate markdown content to specified length
   * Renders markdown, strips HTML, then truncates
   *
   * @param content - Markdown string
   * @param maxLength - Maximum character length
   * @param ellipsis - Append ellipsis if truncated (default: true)
   * @returns Truncated plain text
   *
   * Example:
   * ```typescript
   * const preview = truncateMarkdown('**Very long** text here...', 10)
   * // Returns: 'Very long...'
   * ```
   */
  function truncateMarkdown(content: string, maxLength: number, ellipsis = true): string {
    const plainText = stripMarkdown(content);

    if (plainText.length <= maxLength) {
      return plainText;
    }

    const truncated = plainText.substring(0, maxLength);
    return ellipsis ? `${truncated}...` : truncated;
  }

  return {
    renderMarkdown,
    stripMarkdown,
    truncateMarkdown,
  };
}
