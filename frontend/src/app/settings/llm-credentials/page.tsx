"use client";

import React from "react";
import { LLMCredentialsManager } from "../../../components/features/settings/llm-credentials-manager";
import { useAuth } from "../../../lib/auth-context";

export default function LLMCredentialsPage() {
  const { accessToken, user } = useAuth();

  return (
    <div className="flex flex-col h-full p-6 overflow-y-auto">
      <div className="max-w-3xl w-full mx-auto">
        <LLMCredentialsManager authToken={accessToken ?? undefined} userRole={user?.role} />
      </div>
    </div>
  );
}
