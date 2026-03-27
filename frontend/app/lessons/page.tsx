"use client";

import { useState, useEffect } from "react";
import Nav from "../components/Nav";
import { apiFetch } from "../lib/api";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";

interface Lesson {
  id: string;
  title: string;
  content: string;
  tags: string[];
  source: string;
  session_id: string | null;
  created_at: string;
}

export default function LessonsPage() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [filter, setFilter] = useState<"all" | "user" | "agent">("all");
  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formTags, setFormTags] = useState("");

  const fetchLessons = () => {
    const params = filter !== "all" ? `?source=${filter}` : "";
    apiFetch(`${BACKEND_URL}/api/lessons${params}`)
      .then((r) => r.json())
      .then((data) => setLessons(data.lessons || []))
      .catch(() => {});
  };

  useEffect(() => {
    fetchLessons();
  }, [filter]);

  const handleCreate = async () => {
    if (!formTitle.trim() || !formContent.trim()) return;

    await apiFetch(`${BACKEND_URL}/api/lessons`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: formTitle,
        content: formContent,
        tags: formTags.split(",").map((t) => t.trim()).filter(Boolean),
        source: "user",
      }),
    });

    setFormTitle("");
    setFormContent("");
    setFormTags("");
    setShowForm(false);
    fetchLessons();
  };

  const handleDelete = async (id: string) => {
    await apiFetch(`${BACKEND_URL}/api/lessons/${id}`, { method: "DELETE" });
    fetchLessons();
  };

  return (
    <div className="flex flex-col h-screen">
      <Nav />
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-5xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold">Lessons</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Insights and takeaways from your analyses — saved by you or auto-captured by the agent
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex text-xs border border-[var(--border)] rounded-lg overflow-hidden">
              {(["all", "user", "agent"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 transition-colors ${
                    filter === f
                      ? "bg-[var(--accent)] text-white"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-3 py-1.5 text-xs bg-[var(--accent)] hover:bg-[var(--accent-hover)] rounded-lg transition-colors"
            >
              + New Lesson
            </button>
          </div>
        </div>

        {showForm && (
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 mb-4 space-y-3">
            <input
              type="text"
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              placeholder="Lesson title"
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            />
            <textarea
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              placeholder="What did you learn? What should the agent remember for next time?"
              rows={3}
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-[var(--accent)]"
            />
            <input
              type="text"
              value={formTags}
              onChange={(e) => setFormTags(e.target.value)}
              placeholder="Tags (comma-separated): rnaseq, deseq2, filtering"
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            />
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={!formTitle.trim() || !formContent.trim()}
                className="px-4 py-1.5 text-xs bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 rounded-lg transition-colors"
              >
                Save Lesson
              </button>
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {lessons.length === 0 ? (
          <div className="text-center py-12 text-sm text-[var(--text-secondary)]">
            <p>No lessons yet.</p>
            <p className="mt-1">
              Run an analysis — the agent will auto-capture insights. Or save your own with the button above.
            </p>
            <p className="mt-1">
              You can also type <code className="px-1 py-0.5 rounded bg-[var(--bg-tertiary)]">/lesson your insight here</code> in chat.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {lessons.map((lesson) => (
              <div
                key={lesson.id}
                className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg px-4 py-3"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{lesson.title}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                          lesson.source === "agent"
                            ? "bg-green-900/30 text-green-400"
                            : "bg-blue-900/30 text-blue-400"
                        }`}
                      >
                        {lesson.source}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
                      {lesson.content}
                    </p>
                    <div className="flex gap-1.5 mt-2 flex-wrap">
                      {lesson.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                        >
                          {tag}
                        </span>
                      ))}
                      <span className="text-[10px] text-[var(--text-secondary)]">
                        {new Date(lesson.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(lesson.id)}
                    className="text-xs text-[var(--text-secondary)] hover:text-red-400 ml-3 transition-colors"
                    title="Delete lesson"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
