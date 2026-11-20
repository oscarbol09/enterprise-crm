import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContactForm } from "../components/features/contacts/contact-form";

describe("ContactForm", () => {
  it("validates required fields and email format before invoking onSubmit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(<ContactForm onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: /Guardar Contacto/i }));
    expect(screen.getByText("El nombre es obligatorio.")).toBeInTheDocument();
    expect(screen.getByText("El apellido es obligatorio.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/Nombre/i), "Elena");
    await user.type(screen.getByLabelText(/Apellido/i), "Mendoza");
    await user.type(screen.getByLabelText(/Correo Electrónico/i), "correo-invalido");
    await user.click(screen.getByRole("button", { name: /Guardar Contacto/i }));

    expect(screen.getByText(/Ingrese un correo electrónico válido/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    const emailInput = screen.getByLabelText(/Correo Electrónico/i);
    await user.clear(emailInput);
    await user.type(emailInput, "elena@acme.io");
    await user.click(screen.getByRole("button", { name: /Guardar Contacto/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        first_name: "Elena",
        last_name: "Mendoza",
        email: "elena@acme.io",
      })
    );
  });

  it("autosaves draft to localStorage after 1000ms debounce", () => {
    vi.useFakeTimers();
    try {
      render(<ContactForm onSubmit={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Nombre/i), { target: { value: "Carlos" } });
      expect(localStorage.getItem("crm_contact_form_draft")).toBeNull();

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(localStorage.getItem("crm_contact_form_draft")).toContain("Carlos");
    } finally {
      vi.useRealTimers();
    }
  });
});
