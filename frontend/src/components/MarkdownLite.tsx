import { Fragment, type ReactElement } from 'react';

/**
 * Minimal markdown renderer for LLM output: paragraphs, bullet/numbered
 * lists, **bold**, and `inline code`. The RAG synthesis + agent answers
 * come back as plain markdown-ish text — without this they render as
 * literal asterisks and dashes.
 */
function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 rounded bg-white/10 text-[0.85em] font-telemetry-sm text-status-go"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export default function MarkdownLite({ text }: { text: string }) {
  const lines = text.split('\n');
  const blocks: ReactElement[] = [];
  let listBuffer: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const flushList = (key: string) => {
    if (listBuffer.length === 0) return;
    const items = listBuffer.map((item, i) => <li key={i}>{renderInline(item)}</li>);
    blocks.push(
      listType === 'ol' ? (
        <ol key={key} className="list-decimal ml-5 space-y-1 marker:text-secondary">
          {items}
        </ol>
      ) : (
        <ul key={key} className="list-disc ml-5 space-y-1 marker:text-f1-red">
          {items}
        </ul>
      )
    );
    listBuffer = [];
    listType = null;
  };

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const bulletMatch = line.match(/^[-*]\s+(.*)/);
    const numMatch = line.match(/^\d+[.)]\s+(.*)/);

    if (bulletMatch) {
      if (listType && listType !== 'ul') flushList(`l${idx}`);
      listType = 'ul';
      listBuffer.push(bulletMatch[1]);
      return;
    }
    if (numMatch) {
      if (listType && listType !== 'ol') flushList(`l${idx}`);
      listType = 'ol';
      listBuffer.push(numMatch[1]);
      return;
    }

    flushList(`l${idx}`);
    if (line !== '') {
      blocks.push(
        <p key={`p${idx}`} className="leading-relaxed">
          {renderInline(line)}
        </p>
      );
    }
  });
  flushList('final');

  return <div className="space-y-2.5">{blocks}</div>;
}
