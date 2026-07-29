"use client";

import { AnimatePresence, motion } from "framer-motion";
import { BookOpenText, FileText, History, LogOut, Menu, MessageSquarePlus, Pin, Settings, ShieldCheck, User, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { useAuth } from "@/hooks/useAuth";

const navItems = [
  { label: "New Chat", href: "/dashboard/chat", icon: MessageSquarePlus },
  { label: "Chat History", href: "/dashboard", icon: History },
  { label: "Pinned Chats", href: "/dashboard?view=pinned", icon: Pin },
  { label: "Documents", href: "/dashboard/documents", icon: FileText },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
  { label: "Profile", href: "/dashboard/profile", icon: User },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const sidebar = (
    <div className="flex h-full flex-col bg-card">
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-bold">Insurance AI</p>
          <p className="text-xs text-muted-foreground">Policy intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href.split("?")[0] || (pathname === "/dashboard" && item.label === "Chat History");
          return (
            <Link key={item.label} href={item.href} onClick={() => setOpen(false)} className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-3">
        <div className="mb-3 rounded-lg border border-border bg-muted/40 p-3">
          <p className="truncate text-sm font-semibold">{user?.full_name || "Insurance User"}</p>
          <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
        </div>
        <button onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30">
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </div>
  );

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-background text-foreground">
        <aside className="hidden w-72 shrink-0 border-r border-border lg:block">{sidebar}</aside>

        <AnimatePresence>
          {open && (
            <>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/35 lg:hidden" onClick={() => setOpen(false)} />
              <motion.aside initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={{ duration: 0.2 }} className="fixed inset-y-0 left-0 z-50 w-72 border-r border-border lg:hidden">{sidebar}</motion.aside>
            </>
          )}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-card px-4 lg:px-6">
            <div className="flex items-center gap-3">
              <button className="btn-secondary h-9 w-9 p-0 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu className="h-4 w-4" /></button>
              <div>
                <p className="text-sm font-semibold">Enterprise Insurance Workspace</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="badge"><BookOpenText className="h-3 w-3" /> Chroma knowledge base</span>
                  <span className="badge">Gemini 1.5 Flash</span>
                  <span className="badge">Latency live after response</span>
                </div>
              </div>
            </div>
            <button className="hidden rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted lg:inline-flex" onClick={() => document.documentElement.classList.toggle("dark")} aria-label="Toggle theme">
              <Settings className="h-4 w-4" />
            </button>
          </header>
          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
