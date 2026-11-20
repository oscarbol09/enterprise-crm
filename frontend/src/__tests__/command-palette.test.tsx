import React, { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandPalette } from "../components/features/navigation/command-palette";

function ControlledPaletteHarness({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <CommandPalette
      isOpen={open}
      onClose={() => setOpen(false)}
      onToggle={() => setOpen((p) => !p)}
      onNavigate={onNavigate}
    />
  );
}

describe("CommandPalette", () => {
  it("opens and closes on Ctrl+K when controlled and navigates on Enter", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    render(<ControlledPaletteHarness onNavigate={onNavigate} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Open with Ctrl+K
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog", { name: /Paleta de comandos/i })).toBeInTheDocument();

    // Filter to Copilot IA and press Enter
    const input = screen.getByRole("combobox");
    await user.type(input, "Copilot");
    await user.keyboard("{Enter}");

    expect(onNavigate).toHaveBeenCalledWith("/ai");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Toggle open and close again with Ctrl+K
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
