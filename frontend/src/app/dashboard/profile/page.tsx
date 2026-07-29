"use client";

import { ShieldCheck, User } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

export default function ProfilePage() {
  const { user, isAdmin } = useAuth();

  return (
    <div className="h-full overflow-y-auto p-6 lg:p-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
          <p className="mt-2 text-sm text-muted-foreground">Signed-in workspace identity and access role.</p>
        </div>
        <section className="surface p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <User className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-lg font-semibold">{user?.full_name || "Insurance User"}</h2>
              <p className="truncate text-sm text-muted-foreground">{user?.email}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {user?.roles.map((role) => <span key={role.id || role.name} className="badge"><ShieldCheck className="h-3 w-3" />{role.name}</span>)}
                {isAdmin && <span className="badge border-primary/30 text-primary">Admin access</span>}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
