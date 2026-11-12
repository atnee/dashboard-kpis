"""Agregacoes dos indicadores a partir das leituras mensais.

Nenhum indicador derivado e armazenado: economia e emissao sao sempre
recalculadas a partir da energia e dos parametros do mes correspondente,
de modo que relatorios antigos mantenham a metodologia vigente na epoca.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

import pandas as pd

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]
MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def rotulo_mes(competencia: str) -> str:
    ano, mes = competencia.split("-")
    return f"{MESES_ABREV[int(mes) - 1]}/{ano[2:]}"


def rotulo_extenso(competencia: str) -> str:
    ano, mes = competencia.split("-")
    return f"{MESES_EXTENSO[int(mes) - 1]} de {ano}"


def competencias_no_intervalo(inicio: str, fim: str) -> list[str]:
    periodo = pd.period_range(start=inicio, end=fim, freq="M")
    return [p.strftime("%Y-%m") for p in periodo]


def intervalo_disponivel(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    linha = conn.execute(
        "SELECT MIN(competencia) AS ini, MAX(competencia) AS fim FROM leitura"
    ).fetchone()
    return (linha["ini"], linha["fim"]) if linha else (None, None)


@dataclass
class BlocoIndicadores:
    """Indicadores de um tipo de leitura (gerada ou perdida) em um periodo."""

    tipo: str
    energia: pd.DataFrame        # linhas: competencia, colunas: unidade (kWh)
    economia: pd.DataFrame       # idem, em R$
    emissao: pd.DataFrame        # idem, em tCO2
    grupos: dict[str, str]       # unidade -> grupo
    cores: dict[str, str]        # unidade -> cor

    @property
    def vazio(self) -> bool:
        return self.energia.empty or float(self.energia.to_numpy().sum()) == 0

    def total_energia(self) -> float:
        return float(self.energia.to_numpy().sum())

    def total_economia(self) -> float:
        return float(self.economia.to_numpy().sum())

    def total_emissao(self) -> float:
        return float(self.emissao.to_numpy().sum())

    def por_grupo(self) -> dict[str, dict[str, float]]:
        saida: dict[str, dict[str, float]] = {}
        for unidade, grupo in self.grupos.items():
            if unidade not in self.energia.columns:
                continue
            acumulado = saida.setdefault(grupo, {"energia": 0.0, "economia": 0.0, "emissao": 0.0})
            acumulado["energia"] += float(self.energia[unidade].sum())
            acumulado["economia"] += float(self.economia[unidade].sum())
            acumulado["emissao"] += float(self.emissao[unidade].sum())
        return {g: v for g, v in saida.items() if abs(v["energia"]) > 1e-9}

    def totais_mensais(self) -> pd.Series:
        return self.energia.sum(axis=1)


def _parametros(conn: sqlite3.Connection, competencias: list[str]) -> pd.DataFrame:
    linhas = conn.execute(
        "SELECT competencia, tarifa_rs_kwh, fator_emissao_tco2_mwh FROM parametro_mensal"
    ).fetchall()
    df = pd.DataFrame([dict(l) for l in linhas])
    if df.empty:
        df = pd.DataFrame(columns=["competencia", "tarifa_rs_kwh", "fator_emissao_tco2_mwh"])
    df = df.set_index("competencia").reindex(competencias)
    # Mes sem parametro proprio herda o ultimo conhecido, e nunca um futuro.
    return df.ffill().bfill().fillna(0.0)


def carregar_bloco(
    conn: sqlite3.Connection,
    inicio: str,
    fim: str,
    tipo: str,
    apenas_painel: bool = True,
    grupos_filtrados: list[str] | None = None,
) -> BlocoIndicadores:
    competencias = competencias_no_intervalo(inicio, fim)
    consulta = """
        SELECT l.competencia, u.nome AS unidade, g.nome AS grupo, u.cor,
               u.ordem, l.energia_kwh
          FROM leitura l
          JOIN unidade u ON u.id = l.unidade_id
          LEFT JOIN grupo g ON g.id = u.grupo_id
         WHERE l.tipo = ? AND l.competencia BETWEEN ? AND ?
    """
    parametros: list = [tipo, inicio, fim]
    if apenas_painel and tipo == "gerada":
        consulta += " AND u.incluir_painel = 1"
    if grupos_filtrados:
        marcadores = ",".join("?" for _ in grupos_filtrados)
        consulta += f" AND g.nome IN ({marcadores})"
        parametros.extend(grupos_filtrados)

    dados = pd.DataFrame([dict(l) for l in conn.execute(consulta, parametros).fetchall()])

    if dados.empty:
        vazio = pd.DataFrame(index=competencias)
        return BlocoIndicadores(tipo, vazio, vazio.copy(), vazio.copy(), {}, {})

    dados = dados.sort_values(["ordem", "unidade"])
    ordem_unidades = list(dict.fromkeys(dados["unidade"]))
    grupos = dict(zip(dados["unidade"], dados["grupo"].fillna("Sem grupo")))
    cores = dict(zip(dados["unidade"], dados["cor"].fillna("#888888")))

    energia = (
        dados.pivot_table(index="competencia", columns="unidade",
                          values="energia_kwh", aggfunc="sum")
        .reindex(index=competencias, columns=ordem_unidades)
        .fillna(0.0)
    )
    # Unidades sem nenhuma energia no periodo nao poluem a legenda do grafico.
    energia = energia.loc[:, energia.sum(axis=0).abs() > 1e-9]

    par = _parametros(conn, competencias)
    economia = energia.mul(par["tarifa_rs_kwh"], axis=0)
    emissao = energia.div(1000.0).mul(par["fator_emissao_tco2_mwh"], axis=0)

    return BlocoIndicadores(tipo, energia, economia, emissao, grupos, cores)


def unidades_inoperantes(
    conn: sqlite3.Connection, competencia: str, limite_kwh: float = 1.0
) -> list[str]:
    """Unidades do painel com geracao nula ou residual na competencia."""
    linhas = conn.execute(
        """SELECT u.nome, COALESCE(l.energia_kwh, 0) AS energia
             FROM unidade u
             LEFT JOIN leitura l
               ON l.unidade_id = u.id AND l.tipo = 'gerada' AND l.competencia = ?
            WHERE u.incluir_painel = 1
            ORDER BY u.ordem""",
        (competencia,),
    ).fetchall()
    return [l["nome"] for l in linhas if l["energia"] <= limite_kwh]


def faixa_sistemas_ativos(conn: sqlite3.Connection, inicio: str, fim: str,
                          limite_kwh: float = 1.0) -> tuple[int, int]:
    """Menor e maior quantidade de sistemas gerando ao longo do periodo."""
    contagens = []
    for competencia in competencias_no_intervalo(inicio, fim):
        linha = conn.execute(
            """SELECT COUNT(*) AS n FROM leitura l
                 JOIN unidade u ON u.id = l.unidade_id
                WHERE l.tipo = 'gerada' AND l.competencia = ?
                  AND u.incluir_painel = 1 AND l.energia_kwh > ?""",
            (competencia, limite_kwh),
        ).fetchone()
        contagens.append(linha["n"])
    contagens = [c for c in contagens if c is not None]
    if not contagens:
        return (0, 0)
    return (min(contagens), max(contagens))


def tabela_por_unidade(gerada: BlocoIndicadores, perdida: BlocoIndicadores,
                       limite_kwh: float = 1.0) -> list[dict]:
    """Consolida geracao, perdas e disponibilidade de cada unidade.

    A disponibilidade e a razao entre o que foi gerado e o que teria sido
    gerado sem interrupcoes, usando a propria estimativa de geracao perdida.
    """
    unidades = list(dict.fromkeys(
        list(gerada.energia.columns) + list(perdida.energia.columns)
    ))
    linhas = []
    for unidade in unidades:
        energia = float(gerada.energia[unidade].sum()) if unidade in gerada.energia else 0.0
        perda = float(perdida.energia[unidade].sum()) if unidade in perdida.energia else 0.0
        economia = float(gerada.economia[unidade].sum()) if unidade in gerada.economia else 0.0
        potencial = energia + perda
        # Meses parados contam apenas depois da entrada em operacao da unidade,
        # para que um sistema recente nao apareca como parado o periodo inteiro.
        meses_parados = 0
        if unidade in gerada.energia:
            serie = gerada.energia[unidade]
            ativos = serie[serie > limite_kwh]
            if not ativos.empty:
                desde = serie.loc[ativos.index[0]:]
                meses_parados = int((desde <= limite_kwh).sum())
        linhas.append({
            "unidade": unidade,
            "grupo": gerada.grupos.get(unidade) or perdida.grupos.get(unidade, "Sem grupo"),
            "energia": energia,
            "perdida": perda,
            "economia": economia,
            "disponibilidade": (energia / potencial) if potencial > 0 else 0.0,
            "meses_parados": meses_parados,
        })
    return sorted(linhas, key=lambda l: -l["energia"])


def resumo_periodo(
    conn: sqlite3.Connection,
    inicio: str,
    fim: str,
    grupos_filtrados: list[str] | None = None,
) -> dict:
    gerada = carregar_bloco(conn, inicio, fim, "gerada", True, grupos_filtrados)
    perdida = carregar_bloco(conn, inicio, fim, "perdida", False, grupos_filtrados)
    minimo, maximo = faixa_sistemas_ativos(conn, inicio, fim)
    return {
        "inicio": inicio,
        "fim": fim,
        "gerada": gerada,
        "perdida": perdida,
        "sistemas_ativos": (minimo, maximo),
        "inoperantes_no_fim": unidades_inoperantes(conn, fim),
        "gerado_em": date.today().isoformat(),
    }
