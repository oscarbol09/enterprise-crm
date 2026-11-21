import fs from "node:fs";
import path from "node:path";
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "../components/features/navigation/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/deals",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({
    user: {
      id: "u-1",
      tenant_id: "t-1",
      tenant_name: "Nordic Systems",
      tenant_slug: "nordic",
      email: "admin@nordic.io",
      full_name: "Elena Mendoza",
      role: "admin",
    },
    accessToken: "tok",
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

function walkSourceFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "mocks") continue;
      results.push(...walkSourceFiles(full));
    } else if (/\.(ts|tsx|css)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

describe("Design System & Copywriting Guardrails", () => {
  const srcRoot = path.resolve(__dirname, "..");
  const sourceFiles = walkSourceFiles(srcRoot);

  it("forbids decorative Sparkles icons, purple/indigo gradients, and oversized radii across UI source", () => {
    const forbiddenPatterns = [
      /\bSparkles\b/,
      /\bbg-gradient-to-/,
      /\bfrom-indigo-/,
      /\bfrom-purple-/,
      /\bto-violet-/,
      /\brounded-2xl\b/,
      /\brounded-3xl\b/,
    ];

    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, "utf8");
      for (const pattern of forbiddenPatterns) {
        expect(
          pattern.test(content),
          `Found disallowed visual pattern ${pattern} in ${path.relative(srcRoot, file)}`
        ).toBe(false);
      }
    }
  });

  it("forbids marketing buzzwords and internal DB acronyms in user-facing UI", () => {
    const bannedCopy = [
      /\bpotencia\b/i,
      /\brevoluciona\b/i,
      /\bsin fisuras\b/i,
      /\beleva tu\b/i,
      /\bsupercharge\b/i,
      /\bgame-changer\b/i,
      /\bcutting-edge\b/i,
      /\bHistorial SCD2\b/,
      /\bSoft-Delete reversible\b/,
      /\bpgvector HNSW\b/,
      /AES-256-GCM de API keys del tenant/,
    ];

    for (const file of sourceFiles) {
      if (!file.endsWith(".tsx")) continue;
      const content = fs.readFileSync(file, "utf8");
      for (const pattern of bannedCopy) {
        expect(
          pattern.test(content),
          `Found banned copy/jargon ${pattern} in ${path.relative(srcRoot, file)}`
        ).toBe(false);
      }
    }
  });

  it("enforces curated IBM Plex typography, warm Stone & Pine tokens, and themed browser primitives", () => {
    const globalsCss = fs.readFileSync(path.join(srcRoot, "app", "globals.css"), "utf8");
    const layoutTsx = fs.readFileSync(path.join(srcRoot, "app", "layout.tsx"), "utf8");

    expect(layoutTsx).toContain("IBM_Plex_Sans");
    expect(layoutTsx).toContain("IBM_Plex_Mono");
    expect(globalsCss).toContain("--primary: 168 58% 26%");
    expect(globalsCss).toContain("::selection");
    expect(globalsCss).toContain("caret-color");
    expect(globalsCss).toContain("prefers-reduced-motion: reduce");
    expect(globalsCss).not.toContain("226 70% 55%");
  });

  it("supports toggling the neutral warm charcoal dark theme from AppShell", async () => {
    const user = userEvent.setup();
    document.documentElement.classList.remove("dark");

    render(
      <AppShell>
        <div>Workspace Content</div>
      </AppShell>
    );

    const toggleBtn = screen.getByRole("button", { name: /Cambiar a modo oscuro/i });
    await user.click(toggleBtn);
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    const lightBtn = screen.getByRole("button", { name: /Cambiar a modo claro/i });
    await user.click(lightBtn);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
