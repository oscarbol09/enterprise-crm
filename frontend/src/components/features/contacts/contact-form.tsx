"use client";

import React, { useCallback, useState, useEffect } from "react";
import { AlertCircle, Briefcase, Building2, Mail, Phone, Save, Wand2 } from "lucide-react";
import { Account } from "../../../types/crm";
import { Button } from "../../ui/button";

export interface ContactFormData {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  job_title?: string;
  account_id?: string;
  lifecycle_stage: "lead" | "marketing_qualified" | "sales_qualified" | "customer" | "churned";
}

interface ContactFormProps {
  initialValues?: Partial<ContactFormData>;
  accounts?: Account[];
  onSubmit: (data: ContactFormData) => Promise<void>;
  onCancel?: () => void;
  isLoading?: boolean;
}

function buildInitialContactState(initialValues?: Partial<ContactFormData>): ContactFormData {
  const base: ContactFormData = {
    first_name: initialValues?.first_name || "",
    last_name: initialValues?.last_name || "",
    email: initialValues?.email || "",
    phone: initialValues?.phone || "",
    job_title: initialValues?.job_title || "",
    account_id: initialValues?.account_id || "",
    lifecycle_stage: initialValues?.lifecycle_stage || "lead",
  };
  if (!initialValues && typeof window !== "undefined") {
    try {
      const saved = localStorage.getItem("crm_contact_form_draft");
      if (saved) {
        return { ...base, ...(JSON.parse(saved) as Partial<ContactFormData>) };
      }
    } catch {
      // Ignore corrupt localStorage drafts
    }
  }
  return base;
}

function capitalizeWord(word: string): string {
  if (!word) return "";
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

export function ContactForm({
  initialValues,
  accounts = [],
  onSubmit,
  onCancel,
  isLoading = false,
}: ContactFormProps) {
  const [formData, setFormData] = useState<ContactFormData>(() =>
    buildInitialContactState(initialValues)
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [lastSavedTimestamp, setLastSavedTimestamp] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const validateField = useCallback((name: keyof ContactFormData, value: string): string | null => {
    switch (name) {
      case "first_name":
        if (!value.trim()) return "El nombre es obligatorio.";
        if (value.trim().length > 100) return "Máximo 100 caracteres.";
        return null;
      case "last_name":
        if (!value.trim()) return "El apellido es obligatorio.";
        if (value.trim().length > 100) return "Máximo 100 caracteres.";
        return null;
      case "email": {
        if (!value.trim()) return "El correo electrónico es obligatorio.";
        const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/;
        if (!emailRegex.test(value.trim())) {
          return "Ingrese un correo electrónico válido (ej. usuario@empresa.com).";
        }
        return null;
      }
      case "phone":
        if (value && value.trim().length > 50) return "El teléfono no puede superar 50 caracteres.";
        return null;
      case "job_title":
        if (value && value.trim().length > 150) return "El cargo no puede superar 150 caracteres.";
        return null;
      default:
        return null;
    }
  }, []);

  const handleChange = (name: keyof ContactFormData, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
    setServerError(null);

    if (touched[name]) {
      const error = validateField(name, value);
      setErrors((prev) => ({
        ...prev,
        [name]: error || "",
      }));
    }
  };

  const handleInferFromEmail = () => {
    const rawEmail = formData.email.trim().toLowerCase();
    if (!rawEmail.includes("@")) return;
    const [localPart, domainPart] = rawEmail.split("@");
    const tokens = localPart.split(/[._-]+/).filter(Boolean);

    setFormData((prev) => {
      const next = { ...prev };
      if (!next.first_name && tokens[0]) {
        next.first_name = capitalizeWord(tokens[0]);
      }
      if (!next.last_name && tokens[1]) {
        next.last_name = capitalizeWord(tokens[1]);
      }
      if (!next.account_id && domainPart && accounts.length > 0) {
        const matchedAcc = accounts.find(
          (a) =>
            (a.website && a.website.toLowerCase().includes(domainPart)) ||
            a.name.toLowerCase().replace(/\s+/g, "").includes(domainPart.split(".")[0])
        );
        if (matchedAcc) {
          next.account_id = matchedAcc.id;
        }
      }
      return next;
    });
  };

  const handleBlur = (name: keyof ContactFormData) => {
    setTouched((prev) => ({ ...prev, [name]: true }));
    const error = validateField(name, formData[name] || "");
    setErrors((prev) => ({
      ...prev,
      [name]: error || "",
    }));
  };

  useEffect(() => {
    const isDirty = formData.first_name || formData.last_name || formData.email;
    if (!isDirty) return;

    const timer = setTimeout(() => {
      try {
        localStorage.setItem("crm_contact_form_draft", JSON.stringify(formData));
        const now = new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        setLastSavedTimestamp(now);
      } catch {
        // Ignore localStorage quota limits
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, [formData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const newErrors: Record<string, string> = {};
    const fieldsToValidate: (keyof ContactFormData)[] = [
      "first_name",
      "last_name",
      "email",
      "phone",
      "job_title",
    ];

    fieldsToValidate.forEach((field) => {
      const err = validateField(field, formData[field] || "");
      if (err) newErrors[field] = err;
    });

    setTouched({
      first_name: true,
      last_name: true,
      email: true,
      phone: true,
      job_title: true,
    });
    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      return;
    }

    try {
      await onSubmit(formData);
      try {
        localStorage.removeItem("crm_contact_form_draft");
      } catch {
        // Ignore storage errors
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error al guardar el contacto en el servidor.";
      setServerError(msg);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-5 p-6 bg-card border border-border rounded-lg shadow-card max-w-2xl w-full"
      noValidate
      aria-label="Formulario de creación de contacto"
    >
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div>
          <h2 className="text-base font-semibold text-foreground">Crear Nuevo Contacto</h2>
          <p className="text-xs text-muted-foreground">
            Registre una persona y vincúlela a su empresa y pipeline comercial.
          </p>
        </div>
        {lastSavedTimestamp && (
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground font-mono">
            <Save className="h-3.5 w-3.5 text-success" />
            <span>Borrador guardado: {lastSavedTimestamp}</span>
          </div>
        )}
      </div>

      {serverError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{serverError}</span>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <div className="flex items-center justify-between">
            <label
              htmlFor="email"
              className="text-xs font-medium text-foreground flex items-center justify-between"
            >
              <span>
                Correo Electrónico Corporativo <span className="text-destructive">*</span>
              </span>
            </label>
            {formData.email.includes("@") && (
              <button
                type="button"
                onClick={handleInferFromEmail}
                className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                <Wand2 className="h-3 w-3" />
                <span>Autocompletar nombre y empresa por dominio</span>
              </button>
            )}
          </div>
          <div className="relative">
            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input
              id="email"
              name="email"
              type="email"
              required
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "email-error" : undefined}
              className={`w-full h-10 pl-9 pr-3 bg-background border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary ${
                errors.email ? "border-destructive focus:ring-destructive" : "border-border"
              }`}
              placeholder="carlos.gomez@empresa.com"
              value={formData.email}
              onChange={(e) => handleChange("email", e.target.value)}
              onBlur={() => handleBlur("email")}
            />
          </div>
          {errors.email && (
            <span id="email-error" className="text-[11px] text-destructive flex items-center gap-1">
              <AlertCircle className="h-3 w-3" /> {errors.email}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="first_name"
            className="text-xs font-medium text-foreground flex items-center justify-between"
          >
            <span>
              Nombre <span className="text-destructive">*</span>
            </span>
          </label>
          <input
            id="first_name"
            name="first_name"
            type="text"
            required
            aria-invalid={!!errors.first_name}
            aria-describedby={errors.first_name ? "first_name-error" : undefined}
            className={`w-full h-10 px-3 bg-background border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary ${
              errors.first_name ? "border-destructive focus:ring-destructive" : "border-border"
            }`}
            placeholder="Ej. Carlos"
            value={formData.first_name}
            onChange={(e) => handleChange("first_name", e.target.value)}
            onBlur={() => handleBlur("first_name")}
          />
          {errors.first_name && (
            <span id="first_name-error" className="text-[11px] text-destructive flex items-center gap-1">
              <AlertCircle className="h-3 w-3" /> {errors.first_name}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="last_name"
            className="text-xs font-medium text-foreground flex items-center justify-between"
          >
            <span>
              Apellido <span className="text-destructive">*</span>
            </span>
          </label>
          <input
            id="last_name"
            name="last_name"
            type="text"
            required
            aria-invalid={!!errors.last_name}
            aria-describedby={errors.last_name ? "last_name-error" : undefined}
            className={`w-full h-10 px-3 bg-background border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary ${
              errors.last_name ? "border-destructive focus:ring-destructive" : "border-border"
            }`}
            placeholder="Ej. Gómez"
            value={formData.last_name}
            onChange={(e) => handleChange("last_name", e.target.value)}
            onBlur={() => handleBlur("last_name")}
          />
          {errors.last_name && (
            <span id="last_name-error" className="text-[11px] text-destructive flex items-center gap-1">
              <AlertCircle className="h-3 w-3" /> {errors.last_name}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="phone" className="text-xs font-medium text-foreground">
            Teléfono Móvil / Directo
          </label>
          <div className="relative">
            <Phone className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input
              id="phone"
              name="phone"
              type="tel"
              className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="+34 600 000 000"
              value={formData.phone}
              onChange={(e) => handleChange("phone", e.target.value)}
              onBlur={() => handleBlur("phone")}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="job_title" className="text-xs font-medium text-foreground">
            Cargo / Posición
          </label>
          <div className="relative">
            <Briefcase
              className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="job_title"
              name="job_title"
              type="text"
              className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="VP de Ventas, CTO, etc."
              value={formData.job_title}
              onChange={(e) => handleChange("job_title", e.target.value)}
              onBlur={() => handleBlur("job_title")}
            />
          </div>
        </div>

        {accounts.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="account_id" className="text-xs font-medium text-foreground">
              Empresa Primaria
            </label>
            <div className="relative">
              <Building2
                className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <select
                id="account_id"
                name="account_id"
                value={formData.account_id || ""}
                onChange={(e) => handleChange("account_id", e.target.value)}
                className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">Sin empresa vinculada</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className={`flex flex-col gap-1.5 ${accounts.length > 0 ? "" : "sm:col-span-2"}`}>
          <label htmlFor="lifecycle_stage" className="text-xs font-medium text-foreground">
            Etapa de Ciclo de Vida
          </label>
          <select
            id="lifecycle_stage"
            name="lifecycle_stage"
            value={formData.lifecycle_stage}
            onChange={(e) =>
              handleChange(
                "lifecycle_stage",
                e.target.value as ContactFormData["lifecycle_stage"]
              )
            }
            className="w-full h-10 px-3 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="lead">Lead Inicial</option>
            <option value="marketing_qualified">Marketing Qualified Lead (MQL)</option>
            <option value="sales_qualified">Sales Qualified Lead (SQL)</option>
            <option value="customer">Cliente Activo</option>
            <option value="churned">Desactivado / Churned</option>
          </select>
        </div>
      </div>

      <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
        {onCancel && (
          <Button type="button" variant="ghost" size="md" onClick={onCancel} disabled={isLoading}>
            Cancelar
          </Button>
        )}
        <Button type="submit" variant="primary" size="md" isLoading={isLoading}>
          Guardar Contacto
        </Button>
      </div>
    </form>
  );
}
