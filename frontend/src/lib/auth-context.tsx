"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { LoginPayload, RegisterWorkspacePayload, UserInfo } from "../types/crm";
import {
  getAccessToken,
  loginUser,
  logoutUser,
  refreshSessionSafe,
  registerWorkspace,
  setAccessToken,
} from "./api-client";

interface AuthContextValue {
  user: UserInfo | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterWorkspacePayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [accessToken, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    let active = true;
    async function bootstrapSession() {
      const existing = getAccessToken();
      if (existing) {
        if (active) setIsLoading(false);
        return;
      }
      const refreshed = await refreshSessionSafe();
      if (active) {
        if (refreshed) {
          setUser(refreshed.user);
          setTokenState(refreshed.access_token);
        } else {
          setUser(null);
          setTokenState(null);
        }
        setIsLoading(false);
      }
    }
    void bootstrapSession();
    return () => {
      active = false;
    };
  }, []);

  const login = async (payload: LoginPayload) => {
    const res = await loginUser(payload);
    setAccessToken(res.access_token);
    setTokenState(res.access_token);
    setUser(res.user);
  };

  const register = async (payload: RegisterWorkspacePayload) => {
    const res = await registerWorkspace(payload);
    setAccessToken(res.access_token);
    setTokenState(res.access_token);
    setUser(res.user);
  };

  const logout = async () => {
    await logoutUser();
    setTokenState(null);
    setUser(null);
  };

  return (
    <AuthContext value={{ user, accessToken, isLoading, login, register, logout }}>
      {children}
    </AuthContext>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
