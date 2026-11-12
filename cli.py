"""Linha de comando do sistema de KPIs fotovoltaicos.

Exemplos:
    python cli.py importar dados/kpis_energia_por_unidade.xlsx
    python cli.py periodo
    python cli.py gerar --inicio 2025-01 --fim 2026-02 --saida saida/kpi.pdf
    python cli.py listar
    python cli.py exportar --id 1 --saida saida/kpi.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from kpi_fv import calculo, db, importador, relatorio
from kpi_fv.formato import moeda, numero


def comando_importar(args) -> None:
    conn = db.iniciar(args.banco)
    resultado = importador.importar_planilha(conn, args.planilha)
    atualizadas = importador.importar_cadastro_sistemas(conn, args.planilha)
    print(resultado.resumo())
    if atualizadas:
        print(f"cadastro de {atualizadas} unidades atualizado")
    for aviso in resultado.avisos:
        print("  aviso:", aviso)


def comando_periodo(args) -> None:
    conn = db.iniciar(args.banco)
    inicio, fim = calculo.intervalo_disponivel(conn)
    if not inicio:
        print("nenhuma leitura importada")
        return
    print(f"dados disponiveis de {inicio} a {fim}")
    resumo = calculo.resumo_periodo(conn, inicio, fim)
    print(f"  geracao   {numero(resumo['gerada'].total_energia(), 1)} kWh | "
          f"{moeda(resumo['gerada'].total_economia())} | "
          f"{numero(resumo['gerada'].total_emissao(), 2)} tCO2")
    print(f"  perdas    {numero(resumo['perdida'].total_energia(), 1)} kWh | "
          f"{moeda(resumo['perdida'].total_economia())} | "
          f"{numero(resumo['perdida'].total_emissao(), 2)} tCO2")


def comando_gerar(args) -> None:
    conn = db.iniciar(args.banco)
    inicio, fim = args.inicio, args.fim
    disponivel_inicio, disponivel_fim = calculo.intervalo_disponivel(conn)
    inicio = inicio or disponivel_inicio
    fim = fim or disponivel_fim
    if not inicio or not fim:
        print("nenhuma leitura importada: rode 'importar' primeiro")
        return

    relatorio_id = relatorio.criar_relatorio(
        conn, inicio, fim, autor=args.autor, revisor=args.revisor
    )
    destino = relatorio.exportar_pdf(conn, relatorio_id, args.saida, logo=args.logo)
    print(f"relatorio {relatorio_id} ({inicio} a {fim}) exportado em {destino}")


def comando_listar(args) -> None:
    conn = db.iniciar(args.banco)
    linhas = relatorio.listar_relatorios(conn)
    if not linhas:
        print("nenhum relatorio gravado")
        return
    for linha in linhas:
        print(f"[{linha['id']}] {linha['inicio']} a {linha['fim']} | "
              f"criado em {linha['criado_em']} | {linha['titulo'][:50]}")


def comando_exportar(args) -> None:
    conn = db.iniciar(args.banco)
    destino = relatorio.exportar_pdf(conn, args.id, args.saida, logo=args.logo)
    print(f"exportado em {destino}")


def principal() -> None:
    parser = argparse.ArgumentParser(description="KPIs de sistemas fotovoltaicos")
    parser.add_argument("--banco", default=str(db.CAMINHO_PADRAO))
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("importar", help="importa a planilha de KPIs")
    p.add_argument("planilha", type=Path)
    p.set_defaults(func=comando_importar)

    p = sub.add_parser("periodo", help="mostra o intervalo e os totais disponiveis")
    p.set_defaults(func=comando_periodo)

    p = sub.add_parser("gerar", help="cria um relatorio e exporta o PDF")
    p.add_argument("--inicio")
    p.add_argument("--fim")
    p.add_argument("--saida", default="saida/relatorio_kpi.pdf")
    p.add_argument("--autor", default="Eng. Ayrton Lucas Lisboa do Nascimento")
    p.add_argument("--revisor", default="Dr. Bruno Santana de Albuquerque")
    p.add_argument("--logo")
    p.set_defaults(func=comando_gerar)

    p = sub.add_parser("listar", help="lista os relatorios gravados")
    p.set_defaults(func=comando_listar)

    p = sub.add_parser("exportar", help="exporta novamente um relatorio gravado")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--saida", default="saida/relatorio_kpi.pdf")
    p.add_argument("--logo")
    p.set_defaults(func=comando_exportar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    principal()
