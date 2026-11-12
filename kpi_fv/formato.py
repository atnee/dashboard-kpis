"""Formatacao numerica em padrao brasileiro, independente de locale do sistema."""

from __future__ import annotations


def numero(valor: float | None, casas: int = 2) -> str:
    if valor is None:
        return "-"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def moeda(valor: float | None, casas: int = 2) -> str:
    if valor is None:
        return "-"
    return "R$ " + numero(valor, casas)


def energia(valor: float | None, casas: int = 0, unidade: str = "kWh") -> str:
    if valor is None:
        return "-"
    return f"{numero(valor, casas)} {unidade}"


FILTROS_JINJA = {
    "numero": numero,
    "moeda": moeda,
    "energia": energia,
}


def energia_curta(valor: float | None) -> str:
    """Valor de destaque: MWh a partir de 1.000 kWh, sem a unidade."""
    if valor is None:
        return "-"
    if abs(valor) >= 100000:
        return numero(valor / 1000, 0)
    if abs(valor) >= 1000:
        return numero(valor / 1000, 1)
    return numero(valor, 0)


def unidade_energia(valor: float | None) -> str:
    return "MWh" if valor and abs(valor) >= 1000 else "kWh"


def moeda_curta(valor: float | None) -> str:
    return moeda(valor, 0)


def percentual(valor: float | None, casas: int = 0) -> str:
    if valor is None:
        return "-"
    return numero(valor * 100, casas) + "%"


FILTROS_JINJA.update({
    "energia_curta": energia_curta,
    "unidade_energia": unidade_energia,
    "moeda_curta": moeda_curta,
    "percentual": percentual,
})
