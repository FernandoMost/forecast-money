"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/transactions", label: "Transactions" },
  { href: "/trends", label: "Trends" },
  { href: "/upload", label: "Upload" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-8">
      <span className="font-bold text-gray-900 text-lg tracking-tight">
        Forecast Money
      </span>
      <div className="flex gap-1">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              pathname === link.href
                ? "bg-indigo-50 text-indigo-700"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
      <div className="ml-auto text-xs text-gray-400">local mode — data never leaves your machine</div>
    </nav>
  );
}
