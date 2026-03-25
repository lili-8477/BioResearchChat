"use client";

import { useState, useRef, useEffect } from "react";

interface DataFile {
  filename: string;
  size_mb: number;
  container_path: string;
}

interface DataUploadProps {
  backendUrl: string;
}

export default function DataUpload({ backendUrl }: DataUploadProps) {
  const [files, setFiles] = useState<DataFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/data/files`);
      const data = await res.json();
      setFiles(data.files || []);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [backendUrl]);

  const handleUpload = async (file: File) => {
    if (file.size > 5 * 1024 * 1024 * 1024) {
      setError("File exceeds 5GB limit");
      return;
    }

    setUploading(true);
    setProgress(`Uploading ${file.name}...`);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${backendUrl}/api/data/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }

      const data = await res.json();
      setProgress(`Uploaded: ${data.filename} (${data.size_mb} MB) → ${data.container_path}`);
      await fetchFiles();
    } catch (err: any) {
      setError(err.message || "Upload failed");
      setProgress(null);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (filename: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/data/files/${filename}`, {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchFiles();
      }
    } catch {
      // ignore
    }
  };

  const formatSize = (mb: number) => {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    if (mb >= 1) return `${mb.toFixed(1)} MB`;
    return `${(mb * 1024).toFixed(0)} KB`;
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              handleUpload(file);
              e.target.value = "";
            }
          }}
          className="hidden"
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs border border-[var(--border)] rounded-lg hover:bg-[var(--bg-tertiary)] transition-colors text-[var(--text-secondary)] disabled:opacity-40"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          {uploading ? "Uploading..." : "Upload Data"}
        </button>
        <span className="text-xs text-[var(--text-secondary)]">
          Max 5 GB per file. Mounted as /data/user/ in containers.
        </span>
      </div>

      {progress && (
        <div className="text-xs text-[var(--success)]">{progress}</div>
      )}
      {error && (
        <div className="text-xs text-[var(--error)]">{error}</div>
      )}

      {files.length > 0 && (
        <div className="border border-[var(--border)] rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                <th className="text-left px-3 py-2 font-medium">File</th>
                <th className="text-left px-3 py-2 font-medium">Size</th>
                <th className="text-left px-3 py-2 font-medium">Container path</th>
                <th className="px-3 py-2 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.filename} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2 font-mono">{f.filename}</td>
                  <td className="px-3 py-2">{formatSize(f.size_mb)}</td>
                  <td className="px-3 py-2 text-[var(--text-secondary)] font-mono">{f.container_path}</td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => handleDelete(f.filename)}
                      className="text-[var(--text-secondary)] hover:text-[var(--error)] transition-colors"
                      title="Delete"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
