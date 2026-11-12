/* Cálculos e importação independentes da interface. */
(function(root) {
  const norm = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/_/g, ' ').trim().replace(/\s+/g, ' ');
  const number = value => {
    if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
    let s = String(value ?? '').replace(/R\$|\s/g, '');
    if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
    return Number.isFinite(Number(s)) ? Number(s) : 0;
  };
  const validMonth = s => typeof s === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(s) && s >= '1900-01' && s <= '2200-12';
  function month(value) {
    if (value instanceof Date && !isNaN(value)) return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}`;
    const s = String(value ?? '').trim();
    if (/^\d{4}-\d{2}(-\d{2})?([ T].*)?$/.test(s) && validMonth(s.slice(0,7))) return s.slice(0,7);
    const m = s.match(/^(?:\d{1,2}\/)?(\d{1,2})\/(\d{4})$/);
    return m && validMonth(`${m[2]}-${m[1].padStart(2,'0')}`) ? `${m[2]}-${m[1].padStart(2,'0')}` : null;
  }
  function months(start,end) {
    const out=[]; if (!validMonth(start)||!validMonth(end)||start>end) return out;
    let [y,m]=start.split('-').map(Number);
    while (`${y}-${String(m).padStart(2,'0')}`<=end) {out.push(`${y}-${String(m).padStart(2,'0')}`); if(++m>12){m=1;y++;}}
    return out;
  }
  const key = r => `${r.unit}|${r.month}|${r.type}`;
  function importWorkbook(current, workbook, XLSX) {
    if (!workbook.Sheets.photovoltaic) throw Error('A planilha precisa conter a aba photovoltaic.');
    const data=structuredClone(current), map=new Map(data.readings.map(r=>[key(r),r]));
    const aliases=new Map(); data.units.forEach(u=>[u.name,...u.aliases].forEach(a=>aliases.set(norm(a),u)));
    const ignored=new Set(['tempo','total','economia(r$)','economia','economia perdida','reducao de gases do efeito estufa','emissao de gases de efeito estufa','emissao de gases do efeito estufa','tarifa fora ponta (r$/kwh)','fator de emissao de gases do efeito estufa (tco2/mwh)']);
    let count=0; const newUnits=[];
    for(const [sheet,type] of [['photovoltaic','gerada'],['photovoltaic_loss','perdida']]) {
      if(!workbook.Sheets[sheet]) continue;
      const rows=XLSX.utils.sheet_to_json(workbook.Sheets[sheet],{header:1,defval:null});
      const headers=rows.shift()||[];
      for(const row of rows) {
        const date=month(row[0]); if(!date) continue;
        headers.forEach((header,i)=>{
          const n=norm(header); if(i===0||!n||ignored.has(n)||n.startsWith('unnamed'))return;
          let unit=aliases.get(n);
          if(!unit){unit={id:Math.max(0,...data.units.map(u=>u.id))+1,name:String(header).trim(),group:'Sem grupo',capacity:0,area:0,panel:true,aliases:[]};data.units.push(unit);aliases.set(n,unit);newUnits.push(unit.name);}
          const reading={unit:unit.id,month:date,type,value:number(row[i])}; map.set(key(reading),reading);count++;
        });
        const tariffIndex=headers.findIndex(h=>norm(h)==='tarifa fora ponta (r$/kwh)');
        const factorIndex=headers.findIndex(h=>norm(h)==='fator de emissao de gases do efeito estufa (tco2/mwh)');
        if(tariffIndex>=0&&factorIndex>=0&&row[tariffIndex]!=null&&row[factorIndex]!=null&&(type==='gerada'||!data.params[date])) data.params[date]={tariff:number(row[tariffIndex]),factor:number(row[factorIndex])};
      }
    }
    if(!count)throw Error('Nenhuma leitura mensal válida foi encontrada.');
    if(workbook.Sheets.dados_sistema) for(const row of XLSX.utils.sheet_to_json(workbook.Sheets.dados_sistema,{header:1}).slice(1)) {
      const u=aliases.get(norm(row[0])); if(u){let cap=number(row[1]);u.capacity=cap>1000?cap/1000:cap;u.area=number(row[2]);}
    }
    data.readings=[...map.values()]; return {data,count,newUnits};
  }
  function summarize(data,start,end,group='') {
    const dates=months(start,end), units=data.units.filter(u=>!group||u.group===group), ids=new Map(units.map(u=>[u.id,u]));
    const monthly=dates.map(month=>({month,generated:0,lost:0,savings:0,emissions:0}));
    const byMonth=new Map(monthly.map(r=>[r.month,r]));
    const byUnit=new Map(units.map(u=>[u.id,{...u,generated:0,lost:0,savings:0,emissions:0}]));
    const paramDates=Object.keys(data.params).sort(), missing=new Set();
    for(const r of data.readings) {
      const u=ids.get(r.unit), m=byMonth.get(r.month);if(!u||!m||(r.type==='gerada'&&!u.panel))continue;
      const target=byUnit.get(u.id), lost=r.type==='perdida', field=lost?'lost':'generated';m[field]+=r.value;target[field]+=r.value;
      if(!lost){const prior=paramDates.filter(d=>d<=r.month).at(-1);const p=data.params[r.month]||data.params[prior];
        if(!p){missing.add(r.month);continue;}const saving=r.value*p.tariff, emission=r.value/1000*p.factor;
        m.savings+=saving;target.savings+=saving;m.emissions+=emission;target.emissions+=emission;}
    }
    const totals=monthly.reduce((t,m)=>{for(const k of ['generated','lost','savings','emissions'])t[k]+=m[k];return t;},{generated:0,lost:0,savings:0,emissions:0});
    const availability=totals.generated+totals.lost ? totals.generated/(totals.generated+totals.lost)*100 : null;
    return {monthly,units:[...byUnit.values()].sort((a,b)=>b.generated-a.generated),totals,availability,missing:[...missing]};
  }
  function validate(data) {
    const fail=()=>{throw Error('Backup inválido ou incompatível. Os dados atuais foram preservados.');};
    if(!data||data.version!==1||!Array.isArray(data.units)||!Array.isArray(data.readings)||!data.params||typeof data.params!=='object'||!Array.isArray(data.photos)||typeof data.notes!=='string')fail();
    const ids=new Set();
    for(const u of data.units){if(!Number.isInteger(u.id)||ids.has(u.id)||typeof u.name!=='string'||typeof u.group!=='string'||!Array.isArray(u.aliases)||u.aliases.some(a=>typeof a!=='string')||typeof u.panel!=='boolean'||!Number.isFinite(u.capacity)||!Number.isFinite(u.area))fail();ids.add(u.id);}
    const keys=new Set();
    for(const r of data.readings){if(!ids.has(r.unit)||!validMonth(r.month)||!['gerada','perdida'].includes(r.type)||!Number.isFinite(r.value)||keys.has(key(r)))fail();keys.add(key(r));}
    for(const [m,p] of Object.entries(data.params))if(!validMonth(m)||!p||!Number.isFinite(p.tariff)||!Number.isFinite(p.factor)||p.tariff<0||p.factor<0)fail();
    for(const p of data.photos)if(typeof p.id!=='string'||typeof p.caption!=='string'||!ids.has(p.unit)||!validMonth(p.month)||typeof p.src!=='string'||!/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(p.src))fail();
    return data;
  }
  const api={norm,number,month,months,validMonth,key,importWorkbook,summarize,validate};
  if(typeof module!=='undefined')module.exports=api;else root.KPI=api;
})(globalThis);
