"use client";

import { useState } from "react";

interface PaperUploadProps {
  onUrl: (url: string) => void;
  paperUrl: string | null;
}

export default function PaperUpload({ onUrl, paperUrl }: PaperUploadProps) {
  const [urlInput, setUrlInput] = useState("");
  const [showUrlInput, setShowUrlInput] = useState(false);

  const handleUrlSubmit = () => {
    const url = urlInput.trim();
    if (url) {
      onUrl(url);
      setUrlInput("");
      setShowUrlInput(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowUrlInput(!showUrlInput)}
          className={`flex items-center gap-2 px-3 py-1.5 text-xs border rounded-lg transition-colors ${
            showUrlInput
              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
              : "border-[var(--border)] hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
          }`}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
          </svg>
          Paste URL
        </button>

        {paperUrl && (
          <span className="text-xs text-[var(--success)]">
            URL attached — ready to analyze
          </span>
        )}
      </div>

      {showUrlInput && (
        <div className="flex gap-2">
          <input
            type="url"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
            placeholder="https://doi.org/... or https://arxiv.org/abs/..."
            className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-[var(--accent)] transition-colors"
            autoFocus
          />
          <button
            onClick={handleUrlSubmit}
            disabled={!urlInput.trim()}
            className="px-3 py-1.5 text-xs bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 rounded-lg transition-colors"
          >
            Attach
          </button>
        </div>
      )}
    </div>
  );
}
