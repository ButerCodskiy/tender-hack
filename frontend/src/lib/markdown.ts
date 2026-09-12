import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkRehype from 'remark-rehype';
import rehypeStringify from 'rehype-stringify';
import DOMPurify from 'dompurify';

// Hook to ensure links open safely in a new tab
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

// Single unified processor instance
const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype)
  .use(rehypeStringify);

// In-memory cache for parsed markdown to avoid reparsing static messages on every re-render
const CACHE_LIMIT = 200;
const renderCache = new Map<string, string>();

/**
 * Parses markdown text to sanitized HTML string using the unified + remark + rehype pipeline.
 */
export function renderMarkdownToHtml(markdown: string): string {
  if (!markdown) {
    return '';
  }

  const cached = renderCache.get(markdown);
  if (cached !== undefined) {
    return cached;
  }

  try {
    const rawHtml = String(processor.processSync(markdown));
    const cleanHtml = String(
      DOMPurify.sanitize(rawHtml, {
        USE_PROFILES: { html: true },
      })
    );

    if (renderCache.size >= CACHE_LIMIT) {
      // Remove oldest entry
      const firstKey = renderCache.keys().next().value;
      if (firstKey !== undefined) {
        renderCache.delete(firstKey);
      }
    }

    renderCache.set(markdown, cleanHtml);
    return cleanHtml;
  } catch (error) {
    console.error('Failed to parse markdown:', error);
    // Fallback to basic sanitized text
    return String(DOMPurify.sanitize(markdown));
  }
}
