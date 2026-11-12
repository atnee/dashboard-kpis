"""Sistema visual do relatorio.

A cor carrega informacao: cada grupo de sistemas tem uma familia cromatica e
cada unidade recebe um tom dentro da familia do seu grupo. Verde para o que foi
gerado, latao para o que foi perdido por inoperancia.
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt

TINTA = "#16211C"
TINTA_SUAVE = "#6B7A72"
PAPEL = "#FFFFFF"
PAINEL = "#F3F6F3"
GRADE = "#E2E7E2"

VERDE = "#1E5A43"
LATAO = "#A3761D"

# Familias por grupo: do tom mais escuro ao mais claro.
FAMILIAS = {
    "Prefeitura do Campus": ["#13452F", "#236B4B", "#3D8A66", "#68A98B", "#9AC5AD", "#C6DED3"],
    "Projeto SIMA": ["#1F4E6B", "#2E6D8F", "#4A8CAE", "#71A9C6", "#9BC4D9"],
    "E-MOB": ["#7A5B14", "#A3761D", "#C09538", "#D6B268"],
    "CEAMAZON": ["#5A4A63", "#74608020", "#8B7495", "#AB97B2"],
    "Sem grupo": ["#6B7A72", "#8A9790", "#A9B4AE"],
}

# Familia usada nos graficos de perdas, independente do grupo da unidade.
FAMILIA_PERDA = ["#6B4A12", "#A3761D", "#C9972B", "#E0BC63", "#8C5A2B", "#B87A4A",
                 "#D9A87C", "#5F5420", "#8F8232", "#C0B264"]

FONTE = ["Inter", "Carlito", "Calibri", "DejaVu Sans", "sans-serif"]


def cores_por_unidade(grupos: dict[str, str], unidades: list[str],
                      perda: bool = False) -> dict[str, str]:
    """Distribui tons de cada familia entre as unidades do grupo."""
    if perda:
        return {
            unidade: FAMILIA_PERDA[i % len(FAMILIA_PERDA)]
            for i, unidade in enumerate(unidades)
        }

    por_grupo: dict[str, list[str]] = {}
    for unidade in unidades:
        por_grupo.setdefault(grupos.get(unidade, "Sem grupo"), []).append(unidade)

    cores: dict[str, str] = {}
    for grupo, lista in por_grupo.items():
        familia = FAMILIAS.get(grupo, FAMILIAS["Sem grupo"])
        passo = max(1, len(familia) // max(1, len(lista)))
        for i, unidade in enumerate(lista):
            cores[unidade] = familia[(i * passo) % len(familia)]
    return cores


def aplicar_estilo() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONTE,
        "text.color": TINTA,
        "axes.labelcolor": TINTA_SUAVE,
        "axes.edgecolor": GRADE,
        "axes.facecolor": PAPEL,
        "figure.facecolor": PAPEL,
        "xtick.color": TINTA_SUAVE,
        "ytick.color": TINTA_SUAVE,
        "axes.grid": True,
        "grid.color": GRADE,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "legend.frameon": False,
    })


def limpar_eixo(eixo) -> None:
    for lado in ("top", "right", "left"):
        eixo.spines[lado].set_visible(False)
    eixo.spines["bottom"].set_color(GRADE)
    eixo.grid(axis="x", visible=False)


def nova_figura(largura: float, altura: float, dpi: int = 170):
    aplicar_estilo()
    figura, eixo = plt.subplots(figsize=(largura, altura), dpi=dpi)
    limpar_eixo(eixo)
    return figura, eixo
