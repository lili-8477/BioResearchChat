"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Chat" },
  { href: "/skills", label: "Skills" },
  { href: "/lessons", label: "Lessons" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1 px-6 py-2 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
      {links.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              active
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
