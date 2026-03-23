"use client";

import { useEffect, useRef } from "react";
import type { Message } from "../page";
import PlanReview from "./PlanReview";
import ResultsView from "./ResultsView";
import ReactMarkdown from "react-markdown";

interface ChatWindowProps {
  messages: Message[];
  sessionId: string | null;
  backendUrl: string;
}

export default function ChatWindow({ messages, sessionId, backendUrl }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-semibold mb-3">Research Agent</h2>
          <p className="text-[var(--text-secondary)] text-sm leading-relaxed">
            Upload a research paper (PDF) and ask a question. The agent will
            read the paper, plan an analysis, set up a containerized environment,
            write and execute code, and return results.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-xs text-[var(--text-secondary)]">
            <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border)]">
              scRNA-seq analysis
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border)]">
              Bulk RNA-seq DEG
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border)]">
              ChIP-seq peaks
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border)]">
              Spatial transcriptomics
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map((msg, i) => (
        <MessageBubble
          key={i}
          message={msg}
          sessionId={sessionId}
          backendUrl={backendUrl}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageBubble({
  message,
  sessionId,
  backendUrl,
}: {
  message: Message;
  sessionId: string | null;
  backendUrl: string;
}) {
  const { role, content, type, data } = message;

  // User messages
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-[var(--accent)] rounded-2xl rounded-br-md px-4 py-2.5 max-w-[70%] text-sm">
          {content}
        </div>
      </div>
    );
  }

  // System messages (status updates)
  if (type === "system") {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-[var(--text-secondary)] bg-[var(--bg-secondary)] px-3 py-1 rounded-full">
          {content}
        </span>
      </div>
    );
  }

  // Plan display
  if (type === "plan") {
    return (
      <div className="max-w-[85%]">
        <PlanReview content={content} data={data || {}} />
      </div>
    );
  }

  // Code display
  if (type === "code") {
    const lang = (data as Record<string, string>)?.language || "python";
    return (
      <div className="max-w-[85%]">
        <div className="bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)]">
            <span className="text-xs text-[var(--text-secondary)]">
              Generated {lang} script
            </span>
          </div>
          <pre className="p-4 text-xs overflow-x-auto !border-0 !rounded-none !m-0">
            <code>{content}</code>
          </pre>
        </div>
      </div>
    );
  }

  // Execution output
  if (type === "output") {
    return (
      <div className="max-w-[85%]">
        <div className="bg-[#0d1117] border border-[var(--border)] rounded-lg p-4">
          <pre className="text-xs text-green-400 whitespace-pre-wrap font-mono !bg-transparent !border-0 !p-0 !m-0">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  // Results
  if (type === "result") {
    return (
      <div className="max-w-[85%]">
        <ResultsView
          content={content}
          data={data || {}}
          sessionId={sessionId}
          backendUrl={backendUrl}
        />
      </div>
    );
  }

  // Error
  if (type === "error") {
    return (
      <div className="max-w-[85%]">
        <div className="bg-red-900/20 border border-red-800/50 rounded-lg px-4 py-3">
          <p className="text-sm text-red-400">{content}</p>
        </div>
      </div>
    );
  }

  // Default assistant text
  return (
    <div className="max-w-[85%]">
      <div className="bg-[var(--bg-secondary)] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm prose prose-invert prose-sm max-w-none">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
