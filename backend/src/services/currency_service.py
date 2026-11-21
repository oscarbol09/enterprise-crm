"""
Multi-Currency Normalization Engine & Sales Rep Productivity Playbook Service.
Eliminates naive heterogeneous currency summation and locks historical exchange rates on closed deals.
"""

from decimal import ROUND_HALF_UP, Decimal

DEFAULT_USD_RATES: dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "EUR": Decimal("1.080000"),
    "GBP": Decimal("1.270000"),
    "CAD": Decimal("0.720000"),
    "CHF": Decimal("1.130000"),
    "MXN": Decimal("0.050000"),
    "COP": Decimal("0.000250"),
    "BRL": Decimal("0.180000"),
    "CLP": Decimal("0.001050"),
    "PEN": Decimal("0.270000"),
    "ARS": Decimal("0.001000"),
    "JPY": Decimal("0.006600"),
}


def resolve_exchange_rate_to_usd(
    currency: str,
    explicit_rate: Decimal | None = None,
) -> Decimal:
    """
    Returns the exchange rate converting 1 unit of `currency` into `USD`.
    """
    code = currency.strip().upper()
    if code == "USD":
        return Decimal("1.000000")
    if explicit_rate is not None and explicit_rate > Decimal("0"):
        return Decimal(str(explicit_rate)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return DEFAULT_USD_RATES.get(code, Decimal("1.000000"))


def compute_normalized_usd_amount(
    amount: Decimal,
    exchange_rate_to_usd: Decimal,
) -> Decimal:
    """
    Computes exact `Decimal(15, 2)` USD equivalent using accounting `ROUND_HALF_UP`.
    """
    raw = Decimal(str(amount)) * Decimal(str(exchange_rate_to_usd))
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_deal_rep_playbook(
    *,
    deal_title: str,
    stage_name: str,
    stage_position: int,
    amount: Decimal,
    currency: str,
    contact_first_name: str | None,
) -> dict[str, object]:
    """
    Generates an immediate operational payback for the sales rep when keeping deal stages updated:
    a stage-tailored follow-up message draft and concrete next-step checklist.
    """
    recipient = contact_first_name or "equipo"
    formatted_amount = f"{currency} {Decimal(str(amount)):,.2f}"

    if stage_position <= 1:
        subject = f"Próximos pasos tras nuestra conversación inicial — {deal_title}"
        body = (
            f"Hola {recipient},\n\n"
            f"Gracias por el tiempo hoy para revisar {deal_title}. "
            f"Para preparar una evaluación ajustada a su arquitectura, ¿podríamos agendar 20 minutos "
            f"esta semana con el responsable técnico?"
        )
        actions = [
            "Identificar dolor técnico principal y métrica de impacto.",
            "Confirmar quién lidera la evaluación técnica y quién aprueba presupuesto.",
        ]
    elif stage_position == 2:
        subject = f"Validación de requerimientos técnicos — {deal_title}"
        body = (
            f"Hola {recipient},\n\n"
            f"Comparto el resumen de requerimientos validados para {deal_title}. "
            f"Con base en este alcance ({formatted_amount}), estamos preparando la propuesta formal."
        )
        actions = [
            "Registrar al Comprador Económico en el Comité de Compra del Deal.",
            "Confirmar cronograma objetivo de implementación.",
        ]
    elif stage_position == 3:
        subject = f"Propuesta comercial y alcance técnico — {deal_title}"
        body = (
            f"Hola {recipient},\n\n"
            f"Adjunto la propuesta comercial para {deal_title} por {formatted_amount}. "
            f"Quedo atento a sus comentarios para revisar juntos los términos con su equipo."
        )
        actions = [
            "Agendar sesión de revisión de propuesta en vivo (no enviar PDF sin fecha de llamada).",
            "Validar si Compras o Legal requieren revisión de MSA / DPA.",
        ]
    else:
        subject = f"Revisión final de contrato y arranque — {deal_title}"
        body = (
            f"Hola {recipient},\n\n"
            f"Para mantener la fecha de arranque prevista de {deal_title} ({formatted_amount}), "
            f"¿nos confirmas los datos fiscales y el contacto de firma final?"
        )
        actions = [
            "Verificar RUC/NIT y datos de facturación en los campos del trato.",
            "Confirmar fecha exacta de orden de compra.",
        ]

    return {
        "deal_title": deal_title,
        "stage_name": stage_name,
        "suggested_email_subject": subject,
        "suggested_email_body": body,
        "recommended_actions": actions,
    }
