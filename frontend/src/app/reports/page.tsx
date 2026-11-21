"use client";

import React from "react";
import { useAuth } from "../../lib/auth-context";
import { RevenueReportsDashboard } from "../../components/features/reports/revenue-reports-dashboard";

export default function ReportsPage() {
  const { accessToken } = useAuth();
  return <RevenueReportsDashboard authToken={accessToken ?? undefined} />;
}
