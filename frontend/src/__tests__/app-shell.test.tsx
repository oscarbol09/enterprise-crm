import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "../components/features/navigation/app-shell";

const pushMock = vi.fn();
const replaceMock = vi.fn();
const logoutMock = vi.fn(async () => undefined);

let mockPathname = "/deals";
let mockAuthState: {
  user: {
    id: string;
    tenant_id: string;
    tenant_name?: string;
    tenant_slug?: string;
    email: string;
    full_name: string;
    role: string;
  } | null;
  isLoading: boolean;
} = {
  user: null,
  isLoading: false,
};

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
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
    user: mockAuthState.user,
    accessToken: mockAuthState.user ? "tok" : null,
    isLoading: mockAuthState.isLoading,
    login: vi.fn(),
    register: vi.fn(),
    logout: logoutMock,
  }),
}));

describe("AppShell", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    logoutMock.mockClear();
    mockPathname = "/deals";
  });

  it("renders loading banner while session initializes", () => {
    mockAuthState = { user: null, isLoading: true };
    render(
      <AppShell>
        <div>Protected</div>
      </AppShell>
    );
    expect(screen.getByText(/Verificando sesión segura/i)).toBeInTheDocument();
  });

  it("redirects unauthenticated users to /login outside auth route", () => {
    mockAuthState = { user: null, isLoading: false };
    render(
      <AppShell>
        <div>Protected</div>
      </AppShell>
    );
    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
  });

  it("renders children directly on /login without sidebar", () => {
    mockPathname = "/login";
    mockAuthState = { user: null, isLoading: false };
    render(
      <AppShell>
        <div>Login View</div>
      </AppShell>
    );
    expect(screen.getByText("Login View")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Navegación principal/i)).not.toBeInTheDocument();
  });

  it("renders tenant sidebar, opens command palette, and handles logout", async () => {
    const user = userEvent.setup();
    mockPathname = "/deals";
    mockAuthState = {
      isLoading: false,
      user: {
        id: "u-1",
        tenant_id: "t-1",
        tenant_name: "Acme Global",
        email: "admin@acme.io",
        full_name: "Elena Vance",
        role: "admin",
      },
    };

    render(
      <AppShell>
        <div>Workspace Content</div>
      </AppShell>
    );

    expect(screen.getByText("Workspace Content")).toBeInTheDocument();
    expect(screen.getByText("Elena Vance")).toBeInTheDocument();
    expect(screen.getByText(/Acme Global · admin/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Buscar o saltar/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Cerrar sesión/i }));
    expect(logoutMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/login");
  });
});