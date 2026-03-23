"use client";

import { useState, useEffect } from "react";
import Nav from "../components/Nav";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface Skill {
  name: string;
  description: string;
  analysis_type: string;
  base_image: string;
  language: string;
  packages: string[];
  tags: string[];
  code_template: string;
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/skills`)
      .then((r) => r.json())
      .then((data) => setSkills(data.skills || []))
      .catch(() => {});
  }, []);

  const filtered = skills.filter(
    (s) =>
      !filter ||
      s.name.toLowerCase().includes(filter.toLowerCase()) ||
      s.analysis_type.toLowerCase().includes(filter.toLowerCase()) ||
      s.tags.some((t) => t.toLowerCase().includes(filter.toLowerCase()))
  );

  return (
    <div className="flex flex-col h-screen">
      <Nav />
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-5xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold">Pipeline Skills</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Established bioinformatics pipeline templates the agent uses as reference
            </p>
          </div>
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter skills..."
            className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs w-48 focus:outline-none focus:border-[var(--accent)]"
          />
        </div>

        {filtered.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">
            {skills.length === 0 ? "No skills loaded. Check backend connection." : "No matching skills."}
          </p>
        ) : (
          <div className="space-y-3">
            {filtered.map((skill) => (
              <div
                key={skill.name}
                className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg overflow-hidden"
              >
                <button
                  onClick={() => setExpanded(expanded === skill.name ? null : skill.name)}
                  className="w-full text-left px-4 py-3 hover:bg-[var(--bg-tertiary)] transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium text-sm">{skill.name.replace(/_/g, " ")}</span>
                      <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                        {skill.description}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-4 shrink-0">
                      <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-tertiary)]">
                        {skill.base_image}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-tertiary)]">
                        {skill.language}
                      </span>
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        className={`transition-transform ${expanded === skill.name ? "rotate-180" : ""}`}
                      >
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                    </div>
                  </div>

                  <div className="flex gap-1.5 mt-2 flex-wrap">
                    {skill.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-900/30 text-indigo-400"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </button>

                {expanded === skill.name && (
                  <div className="border-t border-[var(--border)]">
                    <div className="px-4 py-2 flex gap-2 flex-wrap text-xs text-[var(--text-secondary)]">
                      <span>Packages:</span>
                      {skill.packages.map((pkg) => (
                        <code key={pkg} className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)]">
                          {pkg}
                        </code>
                      ))}
                    </div>
                    <pre className="px-4 py-3 text-xs overflow-x-auto bg-[var(--bg-tertiary)] max-h-96">
                      <code>{skill.code_template}</code>
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
