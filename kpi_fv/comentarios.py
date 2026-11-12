"""Rascunho automatico dos comentarios, calculado a partir dos indicadores.

O texto gerado e apenas um ponto de partida: todos os comentarios ficam
gravados por relatorio e podem ser editados antes da exportacao.
"""

from __future__ import annotations

from .calculo import rotulo_extenso
from .formato import moeda, numero


def gerar_comentarios(resumo: dict, incluir_vistoria: bool = False) -> list[str]:
    gerada = resumo["gerada"]
    perdida = resumo["perdida"]
    inicio = rotulo_extenso(resumo["inicio"])
    fim = rotulo_extenso(resumo["fim"])
    minimo, maximo = resumo["sistemas_ativos"]

    textos: list[str] = []

    textos.append(
        f"De {inicio} a {fim}, os sistemas fotovoltaicos acompanhados geraram "
        f"aproximadamente {numero(gerada.total_energia() / 1000, 2)} MWh, "
        f"resultando em uma redução estimada de {numero(gerada.total_emissao(), 2)} "
        f"toneladas de Gases do Efeito Estufa (GEE) e em uma economia acumulada "
        f"de cerca de {moeda(gerada.total_economia())}."
    )

    por_grupo = gerada.por_grupo()
    if len(por_grupo) > 1:
        partes = [
            f"{grupo} com {numero(valores['energia'], 1)} kWh"
            for grupo, valores in sorted(
                por_grupo.items(), key=lambda item: -item[1]["energia"]
            )
        ]
        textos.append("A geração do período distribuiu-se entre " + "; ".join(partes) + ".")

    if minimo and maximo and minimo != maximo:
        textos.append(
            f"Ao longo do período, a quantidade de sistemas em operação variou "
            f"entre {minimo} e {maximo}."
        )

    inoperantes = resumo["inoperantes_no_fim"]
    if inoperantes:
        lista = ", ".join(inoperantes)
        verbo = "está inoperante" if len(inoperantes) == 1 else "estão inoperantes"
        textos.append(
            f"Em {rotulo_extenso(resumo['fim'])}, {lista} {verbo}, "
            f"conforme os dados de monitoramento do período."
        )

    if not perdida.vazio:
        textos.append(
            f"As perdas associadas à inoperância de sistemas totalizaram cerca de "
            f"{numero(perdida.total_energia() / 1000, 2)} MWh, o que representa uma "
            f"perda econômica de {moeda(perdida.total_economia())} e emissões "
            f"adicionais de {numero(perdida.total_emissao(), 2)} tCO2."
        )

    if incluir_vistoria:
        textos.append(
            "Foram realizadas vistorias técnicas nos sistemas fotovoltaicos, "
            "conforme detalhado no Anexo I."
        )

    return textos
