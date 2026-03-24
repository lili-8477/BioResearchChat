"use client";

import { useState } from "react";

interface ResultsViewProps {
  content: string;
  data: Record<string, any>;
  sessionId: string | null;
  backendUrl: string;
}

export default function ResultsView({
  content,
  data,
  sessionId,
  backendUrl,
}: ResultsViewProps) {
  const outputFiles = (data.output_files as string[]) || [];
  const [showLessonForm, setShowLessonForm] = useState(false);
  const [lessonText, setLessonText] = useState("");
  const [lessonSaved, setLessonSaved] = useState(false);

  const getFileUrl = (filePath: string) => {
    return `${backendUrl}/api/sessions/${sessionId}/files/${filePath}`;
  };

  const isImage = (path: string) => {
    return /\.(png|jpg|jpeg|svg|gif)$/i.test(path);
  };

  const saveLesson = async () => {
    if (!lessonText.trim()) return;
    try {
      await fetch(`${backendUrl}/api/lessons`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: lessonText.slice(0, 100),
          content: lessonText,
          tags: [],
          source: "user",
          session_id: sessionId,
        }),
      });
      setLessonSaved(true);
      setShowLessonForm(false);
    } catch (err) {
      console.error("Failed to save lesson:", err);
    }
  };

  return (
    <div className="bg-[var(--bg-secondary)] border border-green-800/40 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)] bg-green-900/20">
        <span className="text-xs font-medium text-green-300">
          Analysis Complete
        </span>
        <div className="flex items-center gap-2">
          <a
            href={`${backendUrl}/api/sessions/${sessionId}/download`}
            download
            className="text-[10px] px-2 py-1 rounded bg-green-900/30 border border-green-800/50 text-green-300 hover:bg-green-900/50 transition-colors"
          >
            Download All
          </a>
          <a
            href={`${backendUrl}/api/sessions/${sessionId}/log`}
            download
            className="text-[10px] px-2 py-1 rounded border border-green-800/50 text-green-400 hover:bg-green-900/30 transition-colors"
          >
            Log
          </a>
          {!lessonSaved && (
            <button
              onClick={() => setShowLessonForm(!showLessonForm)}
              className="text-[10px] px-2 py-1 rounded border border-green-800/50 text-green-400 hover:bg-green-900/30 transition-colors"
            >
              Save Lesson
            </button>
          )}
          {lessonSaved && (
            <span className="text-[10px] text-green-400">Lesson saved</span>
          )}
        </div>
      </div>

      <div className="px-4 py-3 text-sm">
        <p>{content}</p>
      </div>

      {showLessonForm && (
        <div className="px-4 pb-3 space-y-2">
          <textarea
            value={lessonText}
            onChange={(e) => setLessonText(e.target.value)}
            placeholder="What's the key takeaway from this analysis? What should the agent remember?"
            rows={2}
            className="w-full bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs resize-none focus:outline-none focus:border-[var(--accent)]"
            autoFocus
          />
          <div className="flex gap-2">
            <button
              onClick={saveLesson}
              disabled={!lessonText.trim()}
              className="px-3 py-1 text-[10px] bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 rounded transition-colors"
            >
              Save
            </button>
            <button
              onClick={() => setShowLessonForm(false)}
              className="px-3 py-1 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {outputFiles.length > 0 && (
        <div className="px-4 pb-4">
          <p className="text-xs text-[var(--text-secondary)] mb-2">
            Output files ({outputFiles.length}):
          </p>

          <div className="grid grid-cols-2 gap-3 mb-3">
            {outputFiles.filter(isImage).map((file) => (
              <a
                key={file}
                href={getFileUrl(file)}
                target="_blank"
                rel="noopener noreferrer"
                className="block"
              >
                <img
                  src={getFileUrl(file)}
                  alt={file}
                  className="rounded border border-[var(--border)] w-full"
                />
                <span className="text-xs text-[var(--text-secondary)] mt-1 block truncate">
                  {file.split("/").pop()}
                </span>
              </a>
            ))}
          </div>

          <div className="space-y-1">
            {outputFiles
              .filter((f) => !isImage(f))
              .map((file) => (
                <a
                  key={file}
                  href={getFileUrl(file)}
                  download
                  className="flex items-center gap-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
                  </svg>
                  {file.split("/").pop()}
                </a>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
