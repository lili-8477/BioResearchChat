"use client";

import { useState, useRef, useEffect } from "react";

interface ChecklistOption {
  value: string;
  label: string;
  description?: string;
}

interface ChecklistData {
  id: string;
  title: string;
  options: ChecklistOption[];
  allow_custom?: boolean;
  custom_placeholder?: string;
}

interface ChecklistGuideProps {
  data: ChecklistData;
  onSubmit: (response: string) => void;
  disabled?: boolean;
}

export default function ChecklistGuide({ data, onSubmit, disabled }: ChecklistGuideProps) {
  const [submitted, setSubmitted] = useState(false);
  const [submittedValue, setSubmittedValue] = useState("");
  const [showCustom, setShowCustom] = useState(false);
  const [customText, setCustomText] = useState("");
  const customRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showCustom) customRef.current?.focus();
  }, [showCustom]);

  const submit = (response: string) => {
    if (submitted || disabled || !response) return;
    setSubmitted(true);
    setSubmittedValue(response);
    onSubmit(response);
  };

  const handleOptionClick = (opt: ChecklistOption) => {
    if (submitted || disabled) return;
    // Clicking a preset option submits immediately
    submit(opt.label);
  };

  const handleCustomSubmit = () => {
    if (customText.trim()) submit(customText.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleCustomSubmit();
    }
  };

  return (
    <div className="max-w-[85%]">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden">
        {/* Title */}
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h3 className="text-sm font-medium">{data.title}</h3>
        </div>

        {/* Options */}
        <div className="p-3 space-y-2">
          {data.options.map((opt) => {
            const isChosen = submitted && submittedValue === opt.label;
            return (
              <button
                key={opt.value}
                onClick={() => handleOptionClick(opt)}
                disabled={submitted || disabled}
                className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all text-sm ${
                  submitted
                    ? isChosen
                      ? "border-[var(--accent)] bg-[var(--accent)]/15 opacity-100"
                      : "border-transparent bg-[var(--bg-tertiary)] opacity-40"
                    : "border-[var(--border)] bg-[var(--bg-tertiary)] hover:border-[var(--accent)]/50 hover:bg-[var(--accent)]/5"
                } ${submitted || disabled ? "cursor-default" : "cursor-pointer"}`}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors ${
                      isChosen
                        ? "border-[var(--accent)] bg-[var(--accent)]"
                        : "border-[var(--text-secondary)]/40"
                    }`}
                  >
                    {isChosen && (
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path d="M1.5 4L3.2 5.7L6.5 2.3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                  <div>
                    <div className="font-medium">{opt.label}</div>
                    {opt.description && (
                      <div className="text-xs text-[var(--text-secondary)] mt-0.5">
                        {opt.description}
                      </div>
                    )}
                  </div>
                </div>
              </button>
            );
          })}

          {/* "Other" option — part of the list */}
          {data.allow_custom && !submitted && (
            <button
              onClick={() => setShowCustom(true)}
              className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all text-sm ${
                showCustom
                  ? "border-[var(--accent)] bg-[var(--accent)]/10"
                  : "border-[var(--border)] bg-[var(--bg-tertiary)] hover:border-[var(--accent)]/50 hover:bg-[var(--accent)]/5"
              } cursor-pointer`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors ${
                    showCustom
                      ? "border-[var(--accent)] bg-[var(--accent)]"
                      : "border-[var(--text-secondary)]/40"
                  }`}
                >
                  {showCustom && (
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path d="M1.5 4L3.2 5.7L6.5 2.3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
                <div className="font-medium">Other</div>
              </div>
            </button>
          )}

          {/* Custom input — appears inline when "Other" is selected */}
          {data.allow_custom && showCustom && !submitted && (
            <div className="flex gap-2 pl-10 pr-1">
              <input
                ref={customRef}
                type="text"
                value={customText}
                onChange={(e) => setCustomText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={data.custom_placeholder || "Type what you need..."}
                className="flex-1 bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors placeholder:text-[var(--text-secondary)]/50"
              />
              <button
                onClick={handleCustomSubmit}
                disabled={!customText.trim()}
                className="px-4 py-2 bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-30 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
              >
                Go
              </button>
            </div>
          )}

          {/* Show custom text after submission */}
          {submitted && data.allow_custom && !data.options.some((o) => o.label === submittedValue) && (
            <div className="px-3 py-2.5 rounded-lg border border-[var(--accent)] bg-[var(--accent)]/15 text-sm">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 w-4 h-4 rounded-full border-2 border-[var(--accent)] bg-[var(--accent)] flex-shrink-0 flex items-center justify-center">
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                    <path d="M1.5 4L3.2 5.7L6.5 2.3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <div className="font-medium">{submittedValue}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
