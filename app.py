"""Aplicativo de indicadores dos sistemas fotovoltaicos.

Execução:
    streamlit run app.py

O aplicativo cobre o ciclo inteiro: importar as leituras, conferir os números do
período, escrever os comentários, anexar as fotos de vistoria e exportar o PDF.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from kpi_fv import calculo, comentarios as mod_comentarios, db, importador, relatorio
from kpi_fv.formato import moeda, numero, percentual

BANCO = Path("dados/kpi.db")
DIR_FOTOS = Path("dados/fotos")
DIR_SAIDA = Path("saida")

st.set_page_config(page_title="KPI fotovoltaico", page_icon="◧", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 1400px; }
      h1, h2, h3 { letter-spacing: -0.01em; }
      div[data-testid="stMetricValue"] { font-size: 1.7rem; color: #1E5A43; }
      div[data-testid="stMetricLabel"] p { font-size: 0.78rem; color: #6B7A72; }
      .perda div[data-testid="stMetricValue"] { color: #A3761D; }
      .legenda { color: #6B7A72; font-size: 0.8rem; margin-top: -0.4rem; }
      .marca { color: #1E5A43; font-weight: 700; letter-spacing: -0.02em; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def conexao():
    return db.iniciar(BANCO)


def paginas_do_pdf(caminho: Path, escala: float = 2.0) -> list:
    """Converte o PDF em imagens para a prévia dentro do aplicativo."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        st.info("Instale pypdfium2 para ver a prévia na tela. O PDF já está "
                "disponível para download.")
        return []
    documento = pdfium.PdfDocument(str(caminho))
    return [pagina.render(scale=escala).to_pil() for pagina in documento]


conn = conexao()
inicio_disp, fim_disp = calculo.intervalo_disponivel(conn)

# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.markdown("<h3 class='marca'>CEAMAZON</h3>", unsafe_allow_html=True)
    st.caption("Indicadores dos sistemas fotovoltaicos")

    if inicio_disp:
        unidades_cadastradas = conn.execute(
            "SELECT COUNT(*) AS n FROM unidade").fetchone()["n"]
        st.success(f"Leituras de {inicio_disp} a {fim_disp}\n\n"
                   f"{unidades_cadastradas} unidades cadastradas")
    else:
        st.warning("Nenhuma leitura no banco. Comece importando a planilha.")

    enviado = st.file_uploader("Planilha de leituras (.xlsx)", type=["xlsx", "xlsm"])
    if enviado is not None and st.button("Importar planilha", type="primary",
                                         width="stretch"):
        destino = Path("dados") / enviado.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(enviado.getbuffer())
        resultado = importador.importar_planilha(conn, destino)
        importador.importar_cadastro_sistemas(conn, destino)
        st.success(resultado.resumo())
        for aviso in resultado.avisos:
            st.warning(aviso)
        st.rerun()

if not inicio_disp:
    st.title("Comece importando a planilha de leituras")
    st.write("Use o campo na barra lateral. O importador aceita o formato atual, "
             "com as abas de geração e de perdas, uma linha por mês e uma coluna "
             "por unidade.")
    st.stop()


# --------------------------------------------------------------------- relatório
aba_relatorio, aba_dados, aba_vistorias, aba_unidades = st.tabs(
    ["Relatório", "Leituras e parâmetros", "Vistorias", "Unidades"]
)

with aba_relatorio:
    opcoes = calculo.competencias_no_intervalo(inicio_disp, fim_disp)
    coluna_inicio, coluna_fim, coluna_grupos = st.columns([1, 1, 2])
    inicio = coluna_inicio.selectbox("Primeira competência", opcoes, index=0)
    fim = coluna_fim.selectbox("Última competência", opcoes, index=len(opcoes) - 1)
    grupos = [l["nome"] for l in conn.execute(
        "SELECT nome FROM grupo ORDER BY ordem").fetchall()]
    selecionados = coluna_grupos.multiselect("Grupos incluídos", grupos, default=grupos)

    if fim < inicio:
        st.error("A última competência precisa ser igual ou posterior à primeira.")
        st.stop()

    resumo = calculo.resumo_periodo(conn, inicio, fim, selecionados or None)
    gerada, perdida = resumo["gerada"], resumo["perdida"]
    potencial = gerada.total_energia() + perdida.total_energia()

    colunas = st.columns(3)
    colunas[0].metric("Energia gerada", f"{numero(gerada.total_energia() / 1000, 1)} MWh")
    colunas[1].metric("Economia", moeda(gerada.total_economia(), 0))
    colunas[2].metric("Emissões evitadas", f"{numero(gerada.total_emissao(), 2)} tCO2")

    st.markdown("<div class='perda'>", unsafe_allow_html=True)
    colunas = st.columns(3)
    colunas[0].metric("Geração perdida", f"{numero(perdida.total_energia() / 1000, 1)} MWh",
                      delta=f"{percentual(perdida.total_energia() / potencial) if potencial else '-'} do potencial",
                      delta_color="off")
    colunas[1].metric("Economia não obtida", moeda(perdida.total_economia(), 0))
    colunas[2].metric("Emissões não evitadas", f"{numero(perdida.total_emissao(), 2)} tCO2")
    st.markdown("</div>", unsafe_allow_html=True)

    if resumo["inoperantes_no_fim"]:
        st.warning("Sem geração em " + calculo.rotulo_mes(fim) + ": "
                   + ", ".join(resumo["inoperantes_no_fim"]))

    st.divider()

    coluna_texto, coluna_ficha = st.columns([3, 2])

    with coluna_texto:
        st.subheader("Comentários do período")
        chave = f"comentarios_{inicio}_{fim}"
        if chave not in st.session_state:
            st.session_state[chave] = "\n\n".join(mod_comentarios.gerar_comentarios(resumo))
        st.text_area("Um comentário por parágrafo", key=chave, height=260,
                     label_visibility="collapsed")
        if st.button("Refazer rascunho a partir dos dados"):
            st.session_state[chave] = "\n\n".join(mod_comentarios.gerar_comentarios(resumo))
            st.rerun()

    with coluna_ficha:
        st.subheader("Identificação")
        titulo = st.text_input("Título", relatorio.TITULO_PADRAO)
        subtitulo = st.text_input("Subtítulo", relatorio.SUBTITULO_PADRAO)
        autor = st.text_input("Elaborado por", "Eng. Ayrton Lucas Lisboa do Nascimento")
        revisor = st.text_input("Revisado por", "Dr. Bruno Santana de Albuquerque")
        logo = st.file_uploader("Logotipo do cabeçalho", type=["png", "jpg", "jpeg"])

    st.subheader("Desempenho por unidade")
    tabela = pd.DataFrame(calculo.tabela_por_unidade(gerada, perdida))
    if not tabela.empty:
        exibicao = tabela.rename(columns={
            "unidade": "Unidade", "grupo": "Grupo", "energia": "Gerado (kWh)",
            "perdida": "Perdido (kWh)", "economia": "Economia (R$)",
            "disponibilidade": "Disponibilidade", "meses_parados": "Meses sem gerar",
        })
        st.dataframe(
            exibicao, hide_index=True, width="stretch",
            column_config={
                "Gerado (kWh)": st.column_config.NumberColumn(format="%.0f"),
                "Perdido (kWh)": st.column_config.NumberColumn(format="%.0f"),
                "Economia (R$)": st.column_config.NumberColumn(format="%.2f"),
                "Disponibilidade": st.column_config.ProgressColumn(
                    format="%.0f%%", min_value=0, max_value=1),
            },
        )

    st.divider()
    acao_pdf, acao_previa = st.columns([1, 1])
    gerar = acao_pdf.button("Gerar PDF do período", type="primary",
                            width="stretch")
    prever = acao_previa.button("Gerar e ver na tela", width="stretch")

    if gerar or prever:
        caminho_logo = None
        if logo is not None:
            caminho_logo = Path("dados") / f"logo_{logo.name}"
            caminho_logo.write_bytes(logo.getbuffer())
        relatorio_id = relatorio.criar_relatorio(
            conn, inicio, fim, titulo=titulo, subtitulo=subtitulo,
            autor=autor, revisor=revisor,
            comentarios_iniciais=[t for t in st.session_state[chave].split("\n\n") if t.strip()],
            grupos_filtrados=selecionados or None,
        )
        st.session_state["relatorio_atual"] = relatorio_id

        nome = f"kpi_{inicio}_{fim}_{datetime.now():%Y%m%d_%H%M}.pdf"
        destino = relatorio.exportar_pdf(conn, relatorio_id, DIR_SAIDA / nome,
                                         selecionados or None, caminho_logo)
        st.success(f"Relatório {relatorio_id} salvo em {destino}")
        st.download_button("Baixar o PDF", destino.read_bytes(), file_name=nome,
                           mime="application/pdf", type="primary")

        if prever:
            for numero_pagina, imagem in enumerate(paginas_do_pdf(destino), start=1):
                st.image(imagem, caption=f"Página {numero_pagina}", width="stretch")

    gravados = relatorio.listar_relatorios(conn)
    if gravados:
        with st.expander(f"Relatórios gravados ({len(gravados)})"):
            for linha in gravados:
                coluna_descricao, coluna_acao = st.columns([4, 1])
                coluna_descricao.write(
                    f"**{linha['inicio']} a {linha['fim']}** · criado em "
                    f"{linha['criado_em'].replace('T', ' ')}"
                )
                if coluna_acao.button("Reemitir", key=f"re_{linha['id']}"):
                    nome = f"kpi_{linha['inicio']}_{linha['fim']}_r{linha['id']}.pdf"
                    destino = relatorio.exportar_pdf(conn, linha["id"], DIR_SAIDA / nome)
                    coluna_acao.download_button(
                        "Baixar", destino.read_bytes(), file_name=nome,
                        mime="application/pdf", key=f"dl_{linha['id']}")


# ------------------------------------------------------------ leituras e parâmetros
with aba_dados:
    st.subheader("Lançar uma leitura")
    unidades = [l["nome"] for l in conn.execute(
        "SELECT nome FROM unidade ORDER BY ordem, nome").fetchall()]
    campos = st.columns([2, 1, 1, 1, 1])
    unidade = campos[0].selectbox("Unidade", unidades)
    competencia = campos[1].text_input("Competência", value=fim_disp)
    tipo = campos[2].selectbox("Tipo", ["gerada", "perdida"])
    energia = campos[3].number_input("Energia (kWh)", min_value=0.0, step=10.0)
    campos[4].write("")
    if campos[4].button("Gravar", width="stretch"):
        conn.execute(
            """INSERT INTO leitura (unidade_id, competencia, tipo, energia_kwh)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (unidade_id, competencia, tipo)
               DO UPDATE SET energia_kwh = excluded.energia_kwh""",
            (db.resolver_unidade(conn, unidade), competencia, tipo, energia),
        )
        conn.commit()
        st.success(f"{unidade} em {competencia}: {numero(energia, 1)} kWh.")

    st.subheader("Tarifa e fator de emissão por mês")
    st.caption("Esses dois valores definem a economia e as emissões de cada "
               "competência. Relatórios antigos continuam usando o valor da época.")
    parametros = pd.read_sql_query(
        "SELECT competencia, tarifa_rs_kwh, fator_emissao_tco2_mwh "
        "FROM parametro_mensal ORDER BY competencia DESC", conn)
    editados = st.data_editor(parametros, num_rows="dynamic", width="stretch",
                              column_config={
                                  "competencia": st.column_config.TextColumn("Competência"),
                                  "tarifa_rs_kwh": st.column_config.NumberColumn(
                                      "Tarifa fora ponta (R$/kWh)", format="%.6f"),
                                  "fator_emissao_tco2_mwh": st.column_config.NumberColumn(
                                      "Fator de emissão (tCO2/MWh)", format="%.6f"),
                              })
    if st.button("Salvar tarifas e fatores"):
        for _, linha in editados.iterrows():
            if not linha["competencia"]:
                continue
            conn.execute(
                """INSERT INTO parametro_mensal
                   (competencia, tarifa_rs_kwh, fator_emissao_tco2_mwh)
                   VALUES (?, ?, ?)
                   ON CONFLICT (competencia) DO UPDATE SET
                     tarifa_rs_kwh = excluded.tarifa_rs_kwh,
                     fator_emissao_tco2_mwh = excluded.fator_emissao_tco2_mwh""",
                (linha["competencia"], float(linha["tarifa_rs_kwh"]),
                 float(linha["fator_emissao_tco2_mwh"])),
            )
        conn.commit()
        st.success("Parâmetros atualizados.")


# -------------------------------------------------------------------- vistorias
with aba_vistorias:
    gravados = relatorio.listar_relatorios(conn)
    if not gravados:
        st.info("Gere um relatório na primeira aba para poder anexar as fotos de vistoria.")
    else:
        rotulos = {f"{l['inicio']} a {l['fim']} (nº {l['id']})": l["id"] for l in gravados}
        escolhido = st.selectbox("Relatório", list(rotulos))
        relatorio_id = rotulos[escolhido]

        unidades_painel = [l["nome"] for l in conn.execute(
            "SELECT nome FROM unidade WHERE incluir_painel = 1 ORDER BY ordem").fetchall()]
        campos = st.columns([1, 1, 2])
        unidade = campos[0].selectbox("Unidade vistoriada", unidades_painel)
        secao = campos[1].text_input("Título da seção no anexo", unidade)
        legenda = campos[2].text_input("Legenda das fotos enviadas agora",
                                       placeholder="Módulo com trinca no vidro")
        imagens = st.file_uploader("Fotos", type=["png", "jpg", "jpeg"],
                                   accept_multiple_files=True)
        if imagens and st.button("Anexar ao relatório", type="primary"):
            DIR_FOTOS.mkdir(parents=True, exist_ok=True)
            for i, imagem in enumerate(imagens, start=1):
                caminho = DIR_FOTOS / f"r{relatorio_id}_{datetime.now():%H%M%S}_{i}_{imagem.name}"
                caminho.write_bytes(imagem.getbuffer())
                relatorio.adicionar_foto(conn, relatorio_id, caminho, secao=secao,
                                         legenda=legenda, unidade=unidade, ordem=i)
            st.success(f"{len(imagens)} foto(s) anexada(s). Reemita o PDF para vê-las.")
            st.rerun()

        fotos = conn.execute(
            "SELECT id, secao, legenda, arquivo FROM foto WHERE relatorio_id = ? "
            "ORDER BY secao, ordem", (relatorio_id,)).fetchall()
        if fotos:
            st.caption(f"{len(fotos)} foto(s) no anexo")
            for foto in fotos:
                colunas = st.columns([1, 3, 1])
                if Path(foto["arquivo"]).exists():
                    colunas[0].image(foto["arquivo"], width=140)
                colunas[1].write(f"**{foto['secao']}**  \n{foto['legenda']}")
                if colunas[2].button("Remover", key=f"rm_{foto['id']}"):
                    conn.execute("DELETE FROM foto WHERE id = ?", (foto["id"],))
                    conn.commit()
                    st.rerun()


# --------------------------------------------------------------------- unidades
with aba_unidades:
    st.caption("O grupo define a família de cores nos gráficos e os totais do "
               "relatório. Unidades fora do painel entram apenas nos gráficos de "
               "geração perdida.")
    unidades = pd.read_sql_query(
        """SELECT u.id, u.nome, g.nome AS grupo, u.capacidade_kwp, u.area_m2,
                  u.incluir_painel, u.ordem
             FROM unidade u LEFT JOIN grupo g ON g.id = u.grupo_id
            ORDER BY u.ordem, u.nome""", conn)
    grupos = [l["nome"] for l in conn.execute(
        "SELECT nome FROM grupo ORDER BY ordem").fetchall()]
    editadas = st.data_editor(
        unidades, width="stretch", hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("nº", disabled=True),
            "nome": st.column_config.TextColumn("Unidade", disabled=True),
            "grupo": st.column_config.SelectboxColumn("Grupo", options=grupos),
            "capacidade_kwp": st.column_config.NumberColumn("Potência (kWp)", format="%.2f"),
            "area_m2": st.column_config.NumberColumn("Área (m²)", format="%.1f"),
            "incluir_painel": st.column_config.CheckboxColumn("No painel"),
            "ordem": st.column_config.NumberColumn("Ordem"),
        })
    if st.button("Salvar unidades", type="primary"):
        for _, linha in editadas.iterrows():
            grupo = conn.execute("SELECT id FROM grupo WHERE nome = ?",
                                 (linha["grupo"],)).fetchone()
            conn.execute(
                """UPDATE unidade SET grupo_id = ?, capacidade_kwp = ?, area_m2 = ?,
                                      incluir_painel = ?, ordem = ?
                    WHERE id = ?""",
                (grupo["id"] if grupo else None, linha["capacidade_kwp"],
                 linha["area_m2"], int(bool(linha["incluir_painel"])),
                 int(linha["ordem"]), int(linha["id"])),
            )
        conn.commit()
        st.success("Cadastro atualizado.")
