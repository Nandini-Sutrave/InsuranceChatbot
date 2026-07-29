"use client";

import React, { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

interface AuthGuardProps {
  children: React.ReactNode;
  adminOnly?: boolean;
}

export function AuthGuard({ children, adminOnly = false }: AuthGuardProps) {
  const { isAuthenticated, isLoading, isAdmin, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      // Redirect to login page and preserve the path they were trying to access
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
    } else if (adminOnly && !isAdmin) {
      // Authenticated but lacks admin permissions - route to basic chat/dashboard
      router.push("/dashboard");
    }
  }, [isAuthenticated, isLoading, isAdmin, adminOnly, router, pathname]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background text-foreground">
        <div className="relative flex items-center justify-center">
          {/* Pulsing glow background effect */}
          <div className="absolute h-32 w-32 rounded-full bg-primary/20 blur-xl animate-pulse"></div>
          <div className="h-12 w-12 rounded-full border-4 border-muted border-t-primary animate-spin"></div>
        </div>
        <p className="mt-4 text-sm font-medium text-muted-foreground tracking-wider animate-pulse">
          VERIFYING SESSION SECURELY...
        </p>
      </div>
    );
  }

  // Double check authorization parameters before rendering children
  if (!isAuthenticated) {
    return null;
  }

  if (adminOnly && !isAdmin) {
    return null;
  }

  return <>{children}</>;
}
