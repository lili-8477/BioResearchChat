"use client";

import ReactMarkdown from "react-markdown";

interface PlanReviewProps {
  content: string;
  data: Record<string, any>;
}

export default function PlanReview({ content, data }: PlanReviewProps) {
  return (
    <div className="bg-[var(--bg-secondary)] border border-indigo-800/40 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)] bg-indigo-900/20">
        <span className="text-xs font-medium text-indigo-300">
          Analysis Plan
        </span>
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          {data.base_image && (
            <span className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)]">
              {String(data.base_image)}
            </span>
          )}
          {data.language && (
            <span className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)]">
              {String(data.language)}
            </span>
          )}
        </div>
      </div>

      <div className="px-4 py-3 prose prose-invert prose-sm max-w-none text-sm">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>

      <div className="px-4 py-2.5 border-t border-[var(--border)] bg-yellow-900/10">
        <p className="text-xs text-yellow-400/80">
          Reply <strong>approve</strong> to execute this plan, or describe changes.
        </p>
      </div>
    </div>
  );
}
