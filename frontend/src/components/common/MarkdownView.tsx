import React, { useMemo } from 'react';
import clsx from 'clsx';
import { renderMarkdownToHtml } from '../../lib/markdown';

interface MarkdownViewProps {
  content: string;
  className?: string;
}

export const MarkdownView: React.FC<MarkdownViewProps> = ({ content, className }) => {
  const html = useMemo(() => renderMarkdownToHtml(content), [content]);

  return (
    <div
      className={clsx('markdown-content', className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};
