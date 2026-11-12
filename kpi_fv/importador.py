"""Importacao da planilha de KPIs (geracao, perdas e parametros mensais)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import db

COLUNAS_IGNORADAS = {
    "tempo", "total", "economia(r$)", "economia", "economia perdida",
    "reducao de gases do efeito estufa", "emissao de gases de efeito estufa",
    "emissao de gases do efeito estufa",
    "tarifa fora ponta (r$/kwh)",
    "fator de emissao de gases do efeito estufa (tco2/mwh)",
}

COL_TARIFA = "tarifa fora ponta (r$/kwh)"
COL_FATOR = "fator de emissao de gases do efeito estufa (tco2/mwh)"


@dataclass
class ResultadoImportacao:
    leituras: int = 0
    competencias: int = 0
    parametros: int = 0
    unidades_novas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        partes = [
            f"{self.leituras} leituras gravadas",
            f"{self.competencias} competencias",
            f"{self.parametros} parametros mensais",
        ]
        if self.unidades_novas:
            partes.append("unidades criadas: " + ", ".join(self.unidades_novas))
        return "; ".join(partes)


def _numero(valor) -> float:
    """Converte celulas da planilha em float. Trata '-', vazio e texto."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if texto in {"", "-", "–", "—"}:
        return 0.0
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Mantem apenas as linhas cujo primeiro campo e uma data valida.

    As planilhas trazem, abaixo da serie mensal, blocos de totais anuais que
    precisam ser descartados sem depender da quantidade de linhas.
    """
    df = df.copy()
    df = df.rename(columns={df.columns[0]: "Tempo"})
    df["Tempo"] = pd.to_datetime(df["Tempo"], errors="coerce")
    df = df[df["Tempo"].notna()]
    return df


def importar_planilha(
    conn: sqlite3.Connection,
    caminho: Path | str,
    aba_geracao: str = "photovoltaic",
    aba_perdas: str | None = "photovoltaic_loss",
    criar_unidades: bool = True,
) -> ResultadoImportacao:
    resultado = ResultadoImportacao()
    arquivo = pd.ExcelFile(caminho)
    competencias: set[str] = set()

    tarefas = [(aba_geracao, "gerada")]
    if aba_perdas and aba_perdas in arquivo.sheet_names:
        tarefas.append((aba_perdas, "perdida"))

    for aba, tipo in tarefas:
        if aba not in arquivo.sheet_names:
            resultado.avisos.append(f"aba ausente na planilha: {aba}")
            continue
        df = _preparar(pd.read_excel(arquivo, aba))

        for _, linha in df.iterrows():
            competencia = linha["Tempo"].strftime("%Y-%m")
            competencias.add(competencia)

            for coluna in df.columns:
                if coluna == "Tempo":
                    continue
                chave = db.normalizar(coluna)
                if chave in COLUNAS_IGNORADAS or chave.startswith("unnamed"):
                    continue
                unidade_id = db.resolver_unidade(conn, coluna)
                if unidade_id is None:
                    if not criar_unidades:
                        continue
                    unidade_id = db.criar_unidade(conn, str(coluna).strip())
                    resultado.unidades_novas.append(str(coluna).strip())
                    resultado.avisos.append(
                        f"unidade nao cadastrada criada automaticamente: {coluna}"
                    )
                conn.execute(
                    """INSERT INTO leitura (unidade_id, competencia, tipo, energia_kwh)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT (unidade_id, competencia, tipo)
                       DO UPDATE SET energia_kwh = excluded.energia_kwh""",
                    (unidade_id, competencia, tipo, _numero(linha[coluna])),
                )
                resultado.leituras += 1

            # Parametros do mes. A aba de geracao tem prioridade sobre a de perdas.
            tarifa = fator = None
            for coluna in df.columns:
                chave = db.normalizar(coluna)
                if chave == COL_TARIFA:
                    tarifa = _numero(linha[coluna])
                elif chave == COL_FATOR:
                    fator = _numero(linha[coluna])
            if tarifa and fator:
                existe = conn.execute(
                    "SELECT 1 FROM parametro_mensal WHERE competencia = ?", (competencia,)
                ).fetchone()
                if existe is None or tipo == "gerada":
                    conn.execute(
                        """INSERT INTO parametro_mensal
                           (competencia, tarifa_rs_kwh, fator_emissao_tco2_mwh)
                           VALUES (?, ?, ?)
                           ON CONFLICT (competencia) DO UPDATE SET
                             tarifa_rs_kwh = excluded.tarifa_rs_kwh,
                             fator_emissao_tco2_mwh = excluded.fator_emissao_tco2_mwh""",
                        (competencia, tarifa, fator),
                    )
                    resultado.parametros += 1

    conn.commit()
    resultado.competencias = len(competencias)

    faltantes = conn.execute(
        """SELECT DISTINCT l.competencia FROM leitura l
           LEFT JOIN parametro_mensal p ON p.competencia = l.competencia
           WHERE p.competencia IS NULL ORDER BY l.competencia"""
    ).fetchall()
    if faltantes:
        resultado.avisos.append(
            "competencias sem tarifa ou fator de emissao: "
            + ", ".join(f["competencia"] for f in faltantes)
        )
    return resultado


def importar_cadastro_sistemas(
    conn: sqlite3.Connection, caminho: Path | str, aba: str = "dados_sistema"
) -> int:
    """Atualiza capacidade instalada e area a partir da aba de cadastro."""
    arquivo = pd.ExcelFile(caminho)
    if aba not in arquivo.sheet_names:
        return 0
    df = pd.read_excel(arquivo, aba)
    atualizadas = 0
    for _, linha in df.iterrows():
        unidade_id = db.resolver_unidade(conn, linha.iloc[0])
        if unidade_id is None:
            continue
        capacidade = _numero(linha.iloc[1])
        # A planilha mistura W e kW na mesma coluna; acima de 1000 assume-se W.
        if capacidade > 1000:
            capacidade = capacidade / 1000.0
        conn.execute(
            "UPDATE unidade SET capacidade_kwp = ?, area_m2 = ? WHERE id = ?",
            (capacidade, _numero(linha.iloc[2]), unidade_id),
        )
        atualizadas += 1
    conn.commit()
    return atualizadas
