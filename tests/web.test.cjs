const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const KPI=require('../assets/model.js');
const XLSX=require('../assets/vendor/xlsx.full.min.js');
require('../assets/seed.js');
const seed=globalThis.KPI_SEED;
test('seed válido e backup preserva todos os dados',()=>assert.deepEqual(KPI.validate(JSON.parse(JSON.stringify(seed))),seed));
test('importação da planilha não duplica unidades ou leituras',()=>{
  const wb=XLSX.read(fs.readFileSync('dados/kpis_energia_por_unidade.xlsx'),{type:'buffer',cellDates:true});
  const result=KPI.importWorkbook(seed,wb,XLSX);KPI.validate(result.data);
  assert.equal(result.data.units.length,seed.units.length);assert.equal(result.data.readings.length,seed.readings.length);
  const a=new Map(seed.readings.map(r=>[KPI.key(r),r.value]));
  for(const r of result.data.readings)assert.ok(Math.abs(r.value-a.get(KPI.key(r)))<1e-8,JSON.stringify(r));
});
test('indicadores coincidem com a implementação Python',()=>{
  const expected=JSON.parse(execFileSync('python',['-c',`import json
from kpi_fv import db, importador, calculo
c=db.iniciar(':memory:')
importador.importar_planilha(c,'dados/kpis_energia_por_unidade.xlsx')
a,b=calculo.intervalo_disponivel(c)
result=[]
for group in [None,'Projeto SIMA','CEAMAZON','Prefeitura do Campus']:
 r=calculo.resumo_periodo(c,a,b,[group] if group else None)
 result.append(dict(start=a,end=b,group=group,generated=r['gerada'].total_energia(),lost=r['perdida'].total_energia(),savings=r['gerada'].total_economia(),emissions=r['gerada'].total_emissao()))
print(json.dumps(result))`],{encoding:'utf8'}));
  for(const e of expected){const s=KPI.summarize(seed,e.start,e.end,e.group||'');for(const k of ['generated','lost','savings','emissions'])assert.ok(Math.abs(s.totals[k]-e[k])<.000001,`${e.group}: ${k}`);}
});
test('parâmetros nunca são herdados de meses futuros e zero é válido',()=>{
  const data=structuredClone(seed);data.readings=[{unit:1,month:'2025-01',type:'gerada',value:1000},{unit:1,month:'2025-02',type:'gerada',value:1000}];data.params={'2025-02':{tariff:2,factor:0}};
  const s=KPI.summarize(data,'2025-01','2025-02');assert.equal(s.totals.savings,2000);assert.equal(s.totals.emissions,0);assert.deepEqual(s.missing,['2025-01']);
});
test('backup malformado e imagens não seguras são rejeitados',()=>{
  assert.throws(()=>KPI.validate({version:1}));const bad=structuredClone(seed);bad.readings[0].unit=999;assert.throws(()=>KPI.validate(bad));
  const photo=structuredClone(seed);photo.photos=[{id:'x',unit:1,month:'2025-01',caption:'x',src:'javascript:alert(1)'}];assert.throws(()=>KPI.validate(photo));
});
test('datas inválidas e totais anuais não viram competências',()=>{
  for(const s of ['2025','Total 2025','2025-13','31/13/2025',null])assert.equal(KPI.month(s),null);
  assert.equal(KPI.month('01/02/2025'),'2025-02');assert.deepEqual(KPI.months('2025-12','2026-02'),['2025-12','2026-01','2026-02']);
});
