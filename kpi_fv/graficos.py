"""Graficos do relatorio, desenhados com o sistema visual de kpi_fv.tema."""

from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from . import tema
from .calculo import rotulo_mes


def _para_uri(figura) -> str:
    buffer = io.BytesIO()
    figura.savefig(buffer, format="png", bbox_inches="tight",
                   facecolor=tema.PAPEL, pad_inches=0.04)
    plt.close(figura)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _formatador(formato: str):
    if formato == "moeda":
        return FuncFormatter(
            lambda v, _: (f"{v / 1000:,.0f} mil".replace(",", ".")
                          if abs(v) >= 1000 else f"{v:,.0f}".replace(",", "."))
        )
    if formato == "decimal":
        return FuncFormatter(lambda v, _: f"{v:,.1f}".replace(".", ","))
    return FuncFormatter(
        lambda v, _: (f"{v / 1000:,.0f}k".replace(",", ".")
                      if abs(v) >= 1000 else f"{v:,.0f}")
    )


def _rotulo(valor: float, formato: str) -> str:
    if formato == "moeda":
        return "R$ " + f"{valor:,.0f}".replace(",", ".")
    if formato == "decimal":
        return f"{valor:,.2f}".replace(".", ",")
    return f"{valor:,.0f}".replace(",", ".")


def serie_mensal(
    dados: pd.DataFrame,
    cores: dict[str, str],
    rotulo_y: str,
    formato: str = "inteiro",
    largura: float = 10.2,
    altura: float = 2.9,
    legenda: bool = True,
) -> str:
    """Barras empilhadas por unidade com a linha de total sobreposta."""
    figura, eixo = tema.nova_figura(largura, altura)

    if dados is None or dados.empty or dados.shape[1] == 0:
        eixo.text(0.5, 0.5, "Sem leituras no período", ha="center", va="center",
                  fontsize=10, color=tema.TINTA_SUAVE, transform=eixo.transAxes)
        eixo.set_axis_off()
        return _para_uri(figura)

    rotulos = [rotulo_mes(c) for c in dados.index]
    base = pd.Series(0.0, index=dados.index)
    for unidade in dados.columns:
        eixo.bar(rotulos, dados[unidade], bottom=base, label=unidade,
                 color=cores.get(unidade, tema.TINTA_SUAVE), width=0.58,
                 edgecolor=tema.PAPEL, linewidth=0.4)
        base = base + dados[unidade]

    total = dados.sum(axis=1)
    eixo.plot(rotulos, total.values, color=tema.TINTA, linewidth=1.0, alpha=0.5, zorder=5)

    destaques = sorted({int(total.values.argmax()), len(total) - 1})
    for i in destaques:
        eixo.annotate(_rotulo(total.values[i], formato), (rotulos[i], total.values[i]),
                      textcoords="offset points", xytext=(0, 8), ha="center",
                      fontsize=7, fontweight="600", color=tema.TINTA)
        eixo.scatter([rotulos[i]], [total.values[i]], s=9, color=tema.TINTA, zorder=6)

    # Em graficos estreitos com muitos meses, mostra um rotulo sim outro nao.
    passo = max(1, round(len(rotulos) / (largura * 1.5)))
    posicoes = list(range(0, len(rotulos), passo))
    eixo.set_xticks(posicoes)
    eixo.set_xticklabels([rotulos[i] for i in posicoes])

    eixo.set_ylabel(rotulo_y, fontsize=7, labelpad=6)
    eixo.yaxis.set_major_formatter(_formatador(formato))
    eixo.tick_params(axis="x", labelsize=6.8, length=0, pad=3)
    eixo.tick_params(axis="y", labelsize=6.8, length=0)
    eixo.margins(y=0.2, x=0.02)

    if legenda:
        eixo.legend(fontsize=6.6, ncol=min(7, dados.shape[1]), loc="upper center",
                    bbox_to_anchor=(0.5, -0.13), handlelength=0.8, handleheight=0.8,
                    columnspacing=1.4, borderpad=0, labelcolor=tema.TINTA_SUAVE)
    return _para_uri(figura)


def barras_disponibilidade(linhas: list[dict], largura: float = 3.2,
                           altura: float = 2.9) -> str:
    """Disponibilidade por unidade, da pior para a melhor."""
    figura, eixo = tema.nova_figura(largura, altura)

    if not linhas:
        eixo.text(0.5, 0.5, "Sem dados", ha="center", va="center",
                  fontsize=9, color=tema.TINTA_SUAVE, transform=eixo.transAxes)
        eixo.set_axis_off()
        return _para_uri(figura)

    ordenadas = sorted(linhas, key=lambda l: l["disponibilidade"])
    nomes = [l["unidade"] for l in ordenadas]
    valores = [l["disponibilidade"] * 100 for l in ordenadas]
    cores = [tema.LATAO if v < 60 else ("#C09538" if v < 90 else tema.VERDE) for v in valores]

    eixo.barh(nomes, valores, color=cores, height=0.58)
    for nome, valor in zip(nomes, valores):
        eixo.annotate(f"{valor:.0f}%", (valor, nome), xytext=(4, 0),
                      textcoords="offset points", va="center",
                      fontsize=6.8, color=tema.TINTA, fontweight="600")

    eixo.set_xlim(0, 115)
    eixo.set_xticks([])
    eixo.grid(visible=False)
    eixo.spines["bottom"].set_visible(False)
    eixo.tick_params(axis="y", labelsize=7, length=0)
    return _para_uri(figura)


def graficos_do_bloco(bloco, perdido: bool = False) -> dict[str, str]:
    unidades = list(bloco.energia.columns)
    cores = tema.cores_por_unidade(bloco.grupos, unidades, perda=perdido)
    if perdido:
        return {
            "energia": serie_mensal(bloco.energia, cores, "kWh por mês", "inteiro",
                                    largura=6.6, altura=1.95),
            "economia": serie_mensal(bloco.economia, cores, "R$ por mês", "moeda",
                                     largura=5.2, altura=2.0, legenda=False),
            "emissao": serie_mensal(bloco.emissao, cores, "tCO2 por mês", "decimal",
                                    largura=5.2, altura=2.0, legenda=False),
        }
    return {
        "energia": serie_mensal(bloco.energia, cores, "kWh por mês", "inteiro",
                                largura=10.2, altura=2.2),
        "economia": serie_mensal(bloco.economia, cores, "R$ por mês", "moeda",
                                 largura=5.2, altura=2.0, legenda=False),
        "emissao": serie_mensal(bloco.emissao, cores, "tCO2 por mês", "decimal",
                                largura=5.2, altura=2.0, legenda=False),
    }
