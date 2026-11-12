"""Montagem e exportacao do relatorio de KPI (HTML e PDF)."""

from __future__ import annotations

import base64
import mimetypes
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import calculo, comentarios as mod_comentarios, formato, graficos

RAIZ = Path(__file__).resolve().parent
DIR_TEMPLATES = RAIZ / "templates"
ARQUIVO_CSS = RAIZ / "static" / "estilo.css"

TITULO_PADRAO = "Indicadores de desempenho dos sistemas fotovoltaicos"
SUBTITULO_PADRAO = "Projeto de Gestão e Eficiência Energética da UFPA"
EQUIPE_PADRAO = "Equipe de Sistemas Fotovoltaicos e Mobilidade Elétrica"


# ----------------------------------------------------------------- persistencia

def criar_relatorio(
    conn: sqlite3.Connection,
    inicio: str,
    fim: str,
    titulo: str = TITULO_PADRAO,
    subtitulo: str = SUBTITULO_PADRAO,
    equipe: str = EQUIPE_PADRAO,
    autor: str | None = None,
    revisor: str | None = None,
    comentarios_iniciais: list[str] | None = None,
    grupos_filtrados: list[str] | None = None,
) -> int:
    agora = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT INTO relatorio
           (titulo, subtitulo, inicio, fim, equipe, autor, revisor, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (titulo, subtitulo, inicio, fim, equipe, autor, revisor, agora, agora),
    )
    relatorio_id = cur.lastrowid

    if comentarios_iniciais is None:
        resumo = calculo.resumo_periodo(conn, inicio, fim, grupos_filtrados)
        comentarios_iniciais = mod_comentarios.gerar_comentarios(resumo)
    definir_comentarios(conn, relatorio_id, comentarios_iniciais)
    conn.commit()
    return relatorio_id


def definir_comentarios(conn: sqlite3.Connection, relatorio_id: int, textos: list[str]) -> None:
    conn.execute("DELETE FROM comentario WHERE relatorio_id = ?", (relatorio_id,))
    for ordem, texto in enumerate(textos, start=1):
        if texto and texto.strip():
            conn.execute(
                "INSERT INTO comentario (relatorio_id, ordem, texto) VALUES (?, ?, ?)",
                (relatorio_id, ordem, texto.strip()),
            )
    conn.execute(
        "UPDATE relatorio SET atualizado_em = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), relatorio_id),
    )
    conn.commit()


def adicionar_foto(
    conn: sqlite3.Connection,
    relatorio_id: int,
    arquivo: str,
    secao: str,
    legenda: str = "",
    unidade: str | None = None,
    ordem: int = 0,
) -> int:
    from . import db as mod_db

    unidade_id = mod_db.resolver_unidade(conn, unidade) if unidade else None
    cur = conn.execute(
        """INSERT INTO foto (relatorio_id, unidade_id, secao, legenda, arquivo, ordem)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (relatorio_id, unidade_id, secao, legenda, str(arquivo), ordem),
    )
    conn.commit()
    return cur.lastrowid


def listar_relatorios(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM relatorio ORDER BY criado_em DESC"
    ).fetchall()


# ------------------------------------------------------------------- montagem

def _data_uri(caminho: Path | str) -> str | None:
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    tipo = mimetypes.guess_type(caminho.name)[0] or "image/png"
    return f"data:{tipo};base64," + base64.b64encode(caminho.read_bytes()).decode()


def _ordenar_grupos(por_grupo: dict[str, dict[str, float]]) -> list[tuple[str, dict]]:
    preferencia = ["Prefeitura do Campus", "Projeto SIMA", "E-MOB", "CEAMAZON"]

    def chave(item):
        nome = item[0]
        return (preferencia.index(nome) if nome in preferencia else 99, nome)

    return sorted(por_grupo.items(), key=chave)


def _secoes_anexo(conn: sqlite3.Connection, relatorio_id: int) -> list[dict]:
    linhas = conn.execute(
        """SELECT f.secao, f.legenda, f.arquivo, f.ordem, u.nome AS unidade
             FROM foto f LEFT JOIN unidade u ON u.id = f.unidade_id
            WHERE f.relatorio_id = ?
            ORDER BY COALESCE(u.ordem, 999), f.secao, f.ordem, f.id""",
        (relatorio_id,),
    ).fetchall()

    secoes: list[dict] = []
    numero = 0
    for linha in linhas:
        imagem = _data_uri(linha["arquivo"])
        if imagem is None:
            continue
        titulo = linha["secao"] or linha["unidade"] or "Vistoria"
        if not secoes or secoes[-1]["titulo"] != titulo:
            secoes.append({"titulo": titulo, "figuras": []})
        numero += 1
        secoes[-1]["figuras"].append(
            {"numero": numero, "legenda": linha["legenda"] or "", "imagem": imagem}
        )
    return secoes


def montar_contexto(
    conn: sqlite3.Connection,
    relatorio_id: int,
    grupos_filtrados: list[str] | None = None,
    logo: str | Path | None = None,
) -> dict:
    registro = conn.execute(
        "SELECT * FROM relatorio WHERE id = ?", (relatorio_id,)
    ).fetchone()
    if registro is None:
        raise ValueError(f"relatorio {relatorio_id} nao encontrado")

    inicio, fim = registro["inicio"], registro["fim"]
    resumo = calculo.resumo_periodo(conn, inicio, fim, grupos_filtrados)
    gerada, perdida = resumo["gerada"], resumo["perdida"]

    textos = [
        linha["texto"]
        for linha in conn.execute(
            "SELECT texto FROM comentario WHERE relatorio_id = ? ORDER BY ordem",
            (relatorio_id,),
        ).fetchall()
    ]

    tabela = calculo.tabela_por_unidade(gerada, perdida)
    potencial = gerada.total_energia() + perdida.total_energia()
    proporcao = (perdida.total_energia() / potencial) if potencial > 0 else 0.0

    parametro_final = conn.execute(
        "SELECT tarifa_rs_kwh, fator_emissao_tco2_mwh FROM parametro_mensal "
        "WHERE competencia <= ? ORDER BY competencia DESC LIMIT 1", (fim,)
    ).fetchone()

    total_unidades = conn.execute(
        "SELECT COUNT(*) AS n FROM unidade WHERE incluir_painel = 1"
    ).fetchone()["n"]
    ativas = total_unidades - len(resumo["inoperantes_no_fim"])

    secoes = _secoes_anexo(conn, relatorio_id)
    # A chamada ao anexo so entra quando ha fotos, e nao se o autor ja citou.
    if secoes and not any("anexo" in texto.lower() for texto in textos):
        textos.append("Foram realizadas vistorias técnicas nos sistemas "
                      "fotovoltaicos, conforme o registro fotográfico do anexo.")

    return {
        "relatorio": dict(registro),
        "periodo_rotulo": f"{calculo.rotulo_mes(inicio)} a {calculo.rotulo_mes(fim)}",
        "mes_final": calculo.rotulo_mes(fim),
        "gerado_em": datetime.now().strftime("%d/%m/%Y"),
        "graficos_gerada": graficos.graficos_do_bloco(gerada, perdido=False),
        "graficos_perdida": graficos.graficos_do_bloco(perdida, perdido=True),
        "grafico_disponibilidade": graficos.barras_disponibilidade(
            [l for l in tabela if l["energia"] > 0 or l["perdida"] > 0],
            largura=3.6, altura=1.95,
        ),
        "tabela_unidades": tabela,
        "proporcao_perda": formato.percentual(proporcao),
        "unidades_ativas": ativas,
        "unidades_totais": total_unidades,
        "tarifa_final": parametro_final["tarifa_rs_kwh"] if parametro_final else None,
        "fator_final": parametro_final["fator_emissao_tco2_mwh"] if parametro_final else None,
        "grupos_gerada": _ordenar_grupos(gerada.por_grupo()),
        "grupos_perdida": _ordenar_grupos(perdida.por_grupo()),
        "totais_gerada": {
            "energia": gerada.total_energia(),
            "economia": gerada.total_economia(),
            "emissao": gerada.total_emissao(),
        },
        "totais_perdida": {
            "energia": perdida.total_energia(),
            "economia": perdida.total_economia(),
            "emissao": perdida.total_emissao(),
        },
        "comentarios": textos,
        "secoes_anexo": secoes,
        "logo": _data_uri(logo) if logo else None,
        "css": ARQUIVO_CSS.read_text(encoding="utf-8"),
    }


def _ambiente() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(DIR_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters.update(formato.FILTROS_JINJA)

    def formatar(valor, tipo):
        if tipo == "economia":
            return formato.moeda(valor)
        if tipo == "emissao":
            return formato.numero(valor, 2) + " tCO2"
        return formato.energia(valor, 1)

    env.filters["formatar"] = formatar
    return env


def renderizar_html(
    conn: sqlite3.Connection,
    relatorio_id: int,
    grupos_filtrados: list[str] | None = None,
    logo: str | Path | None = None,
) -> str:
    contexto = montar_contexto(conn, relatorio_id, grupos_filtrados, logo)
    return _ambiente().get_template("painel.html").render(**contexto)


def exportar_pdf(
    conn: sqlite3.Connection,
    relatorio_id: int,
    destino: str | Path,
    grupos_filtrados: list[str] | None = None,
    logo: str | Path | None = None,
) -> Path:
    from weasyprint import HTML  # importado aqui para nao pesar a inicializacao

    html = renderizar_html(conn, relatorio_id, grupos_filtrados, logo)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(RAIZ)).write_pdf(str(destino))
    return destino
