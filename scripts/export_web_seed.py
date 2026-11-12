"""Exporta a planilha já versionada para a versão estática do painel."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kpi_fv import db, importador

conn = db.iniciar(':memory:')
source = ROOT / 'dados/kpis_energia_por_unidade.xlsx'
importador.importar_planilha(conn, source)
importador.importar_cadastro_sistemas(conn, source)
units = []
for row in conn.execute('SELECT u.*, g.nome AS grupo FROM unidade u LEFT JOIN grupo g ON g.id=u.grupo_id ORDER BY u.ordem'):
    units.append(dict(id=row['id'], name=row['nome'], group=row['grupo'] or 'Sem grupo',
                      capacity=row['capacidade_kwp'] or 0, area=row['area_m2'] or 0,
                      panel=bool(row['incluir_painel']), aliases=[r[0] for r in conn.execute('SELECT chave FROM alias_unidade WHERE unidade_id=?', (row['id'],))]))
data = dict(version=1, units=units,
            readings=[dict(unit=r['unidade_id'], month=r['competencia'], type=r['tipo'], value=r['energia_kwh']) for r in conn.execute('SELECT * FROM leitura')],
            params={r['competencia']:dict(tariff=r['tarifa_rs_kwh'],factor=r['fator_emissao_tco2_mwh']) for r in conn.execute('SELECT * FROM parametro_mensal')},
            notes='', photos=[])
(ROOT/'assets/seed.js').write_text('globalThis.KPI_SEED = '+json.dumps(data, ensure_ascii=False, separators=(',',':'))+';\n', encoding='utf-8')
print(f"Exportadas {len(data['readings'])} leituras de {len(units)} unidades.")
