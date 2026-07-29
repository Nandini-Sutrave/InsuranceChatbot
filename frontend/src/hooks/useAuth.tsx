"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, setAccessToken, type User } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  startOAuth: (provider: "google" | "microsoft") => Promise<void>;
  logout: () => Promise<void>;
  isAdmin: boolean;
  isPospAgent: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function createOAuthState() {
  const random = new Uint32Array(4);
  crypto.getRandomValues(random);
  return Array.from(random).map((n) => n.toString(16)).join("");
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadUser = async () => {
    const currentUser = await api.me();
    setUser(currentUser);
    return currentUser;
  };

  useEffect(() => {
    const hydrate = async () => {
      try {
        const data = await api.refresh();
        setAccessToken(data.access_token);
        await loadUser();
      } catch {
        setAccessToken("");
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    hydrate();
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const data = await api.login(email, password);
      setAccessToken(data.access_token);
      await loadUser();
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithToken = async (token: string) => {
    setIsLoading(true);
    try {
      setAccessToken(token);
      await loadUser();
    } finally {
      setIsLoading(false);
    }
  };

  const startOAuth = async (provider: "google" | "microsoft") => {
    const state = createOAuthState();
    sessionStorage.setItem(`oauth_state_${provider}`, state);
    const redirectUri = `${window.location.origin}/auth/callback/${provider}`;
    const { redirect_url } = await api.getOAuthUrl(provider, redirectUri, state);
    window.location.href = redirect_url;
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await api.logout();
    } finally {
      setAccessToken("");
      setUser(null);
      setIsLoading(false);
      window.location.href = "/login";
    }
  };

  const roles = useMemo(() => user?.roles.map((role) => role.name) || [], [user]);
  const value = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    loginWithToken,
    startOAuth,
    logout,
    isAdmin: roles.includes("admin"),
    isPospAgent: roles.includes("posp_agent"),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
