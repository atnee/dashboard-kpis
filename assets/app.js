'use strict';
const $=selector=>document.querySelector(selector), $$=selector=>[...document.querySelectorAll(selector)];
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(value,digits=1)=>new Intl.NumberFormat('pt-BR',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value);
const money=value=>new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}).format(value);
const labelMonth=m=>m?new Date(`${m}-15T12:00:00`).toLocaleDateString('pt-BR',{month:'short',year:'2-digit'}).replace('.',''):'';
let data, database, currentTab='overview', summary, saveQueue=Promise.resolve();
function notice(text,error=false){$('#message').textContent=text;$('#message').hidden=false;$('#message').classList.toggle('error',error);}
function openDatabase(){return new Promise((resolve,reject)=>{const request=indexedDB.open('observatorio-solar',1);request.onupgradeneeded=()=>request.result.createObjectStore('state');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}
function readDatabase(){return new Promise((resolve,reject)=>{const r=database.transaction('state').objectStore('state').get('data');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
function persist(next){return new Promise((resolve,reject)=>{if(!database)return reject(Error('O armazenamento do navegador está indisponível. Exporte um backup antes de sair.'));const t=database.transaction('state','readwrite');t.objectStore('state').put(next,'data');t.oncomplete=()=>resolve();t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error||Error('Não foi possível salvar os dados.'));});}
function change(mutator,message){
  saveQueue=saveQueue.then(async()=>{const next=structuredClone(data);await mutator(next);KPI.validate(next);await persist(next);data=next;render();notice(message);$('#storage-status').textContent='● Salvo neste navegador';}).catch(error=>notice(error.message,true));
  return saveQueue;
}
function download(content,name,type){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
function unitOptions(selected){return data.units.map(u=>`<option value="${u.id}" ${u.id===Number(selected)?'selected':''}>${esc(u.name)}</option>`).join('');}
function setTab(tab){currentTab=tab;$$('.panel').forEach(p=>p.hidden=p.id!==tab);$$('.nav').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});$('#page-title').textContent=({overview:'Panorama fotovoltaico',readings:'Leituras e parâmetros',units:'Unidades fotovoltaicas',photos:'Vistorias de campo'})[tab];}
function fillUnitForm(){const form=$('#unit-form'),unit=data.units.find(u=>u.id===Number(form.elements.id.value));for(const key of ['name','group','capacity','area'])form.elements[key].value=unit?.[key]??(key==='name'||key==='group'?'':0);form.elements.panel.checked=unit?unit.panel:true;}
function selectedPhotos(){return data.photos.filter(p=>p.month>=$('#start').value&&p.month<=$('#end').value&&(!$('#group').value||data.units.find(u=>u.id===p.unit)?.group===$('#group').value));}
function photoHTML(p,remove=false){const u=data.units.find(u=>u.id===p.unit);return `<figure><img src="${p.src}" alt="${esc(p.caption)}" loading="${remove?'lazy':'eager'}"><figcaption><strong>${esc(u?.name)} · ${esc(labelMonth(p.month))}</strong><br>${esc(p.caption)}</figcaption>${remove?`<button data-remove-photo="${esc(p.id)}" class="secondary">Remover foto</button>`:''}</figure>`;}
function render(){
  const dates=[...new Set(data.readings.map(r=>r.month))].sort();
  if(!$('#start').value)$('#start').value=dates[0]||new Date().toISOString().slice(0,7);
  if(!$('#end').value)$('#end').value=dates.at(-1)||$('#start').value;
  const groups=[...new Set(data.units.map(u=>u.group))], selectedGroup=$('#group').value;
  $('#group').innerHTML='<option value="">Todos os grupos</option>'+groups.map(g=>`<option ${g===selectedGroup?'selected':''}>${esc(g)}</option>`).join('');
  $('#groups').innerHTML=groups.map(g=>`<option value="${esc(g)}"></option>`).join('');
  if($('#start').value>$('#end').value){notice('A primeira competência deve ser anterior ou igual à última.',true);return;}
  summary=KPI.summarize(data,$('#start').value,$('#end').value,$('#group').value);
  const t=summary.totals;
  $('#period-label').textContent=`${labelMonth($('#start').value)} — ${labelMonth($('#end').value)} · ${$('#group').value||'Todos os grupos'} · ${summary.monthly.length} meses`;
  const metrics=[['Energia gerada',num(t.generated/1000),'MWh produzidos no período','☀'],['Economia estimada',money(t.savings),'Tarifas de cada competência','↗'],['Emissões evitadas',num(t.emissions),'toneladas de CO₂','♧'],['Unidades geradoras',String(summary.units.filter(u=>u.panel&&u.generated>1).length),'Com geração acima de 1 kWh','▦']];
  $('#metrics').innerHTML=metrics.map(([label,value,sub,icon])=>`<article class="metric"><div class="label">${label}<span class="symbol">${icon}</span></div><strong>${value}</strong><small>${sub}</small></article>`).join('');
  const max=Math.max(1,...summary.monthly.map(m=>Math.max(m.generated,m.lost)));
  $('#chart').innerHTML=summary.monthly.length?`<div class="bars" style="min-width:${Math.max(0,summary.monthly.length*35)}px">${summary.monthly.map(m=>`<div class="bar-pair"><div class="bar" role="img" aria-label="${esc(labelMonth(m.month))}: ${num(m.generated)} kWh gerados" title="${esc(labelMonth(m.month))} · Gerada: ${num(m.generated)} kWh" style="height:${Math.max(0,m.generated)/max*100}%"></div><div class="bar lost" role="img" aria-label="${num(m.lost)} kWh perdidos" title="Perdida: ${num(m.lost)} kWh" style="height:${Math.max(0,m.lost)/max*100}%"></div><small>${esc(labelMonth(m.month))}</small></div>`).join('')}</div>`:'<p class="empty">Sem dados para este período.</p>';
  $('#availability').innerHTML=`<div class="ring" style="--angle:${Math.max(0,Math.min(100,summary.availability||0))*3.6}deg"><div class="ring-inner"><strong>${summary.availability===null?'—':num(summary.availability)+'%'}</strong><small>DO POTENCIAL ESTIMADO</small></div></div>`;
  $('#loss-value').textContent=`${num(t.lost/1000)} MWh de geração perdida`;
  $('#unit-summary').innerHTML=summary.units.filter(u=>u.generated||u.lost).map(u=>`<tr><td><strong>${esc(u.name)}</strong><small>${esc(u.group)}</small></td><td>${num(u.generated)}</td><td>${num(u.lost)}</td><td>${money(u.savings)}</td><td><span class="avail">${u.generated+u.lost?num(u.generated/(u.generated+u.lost)*100)+'%':'—'}</span></td></tr>`).join('')||'<tr><td colspan="5" class="empty">Nenhuma leitura no período e grupo selecionados.</td></tr>';
  const unitMap=new Map(data.units.map(u=>[u.id,u]));
  $('#reading-table').innerHTML=data.readings.filter(r=>r.month>=$('#start').value&&r.month<=$('#end').value&&(!$('#group').value||unitMap.get(r.unit).group===$('#group').value)).sort((a,b)=>b.month.localeCompare(a.month)||a.unit-b.unit).map(r=>`<tr><td>${esc(labelMonth(r.month))}</td><td>${esc(unitMap.get(r.unit).name)}</td><td>${r.type==='gerada'?'Gerada':'Perdida'}</td><td>${num(r.value)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">Nenhuma leitura.</td></tr>';
  $$('.unit-select').forEach(select=>{select.innerHTML=unitOptions(select.value);});
  const oldUnit=$('#edit-unit').value;$('#edit-unit').innerHTML=unitOptions(oldUnit)+'<option value="new">+ Nova unidade</option>';fillUnitForm();
  $('#unit-cards').innerHTML=data.units.map(u=>`<div class="unit-card"><strong>${esc(u.name)}</strong><p>${esc(u.group)}</p><span class="hint">${num(u.capacity)} kWp · ${num(u.area)} m²<br>${u.panel?'Geração incluída no painel':'Somente perdas no painel'}</span></div>`).join('');
  $('#notes').value=data.notes;$('.notes').dataset.notes=data.notes||'Sem observações registradas.';
  const photos=selectedPhotos();$('#photo-gallery').innerHTML=photos.map(p=>photoHTML(p,true)).join('')||'<p class="empty">Nenhuma foto no período e grupo selecionados.</p>';
  $('#print-photos').innerHTML=photos.length?'<h2>Anexo · Registro fotográfico</h2>'+photos.map(p=>photoHTML(p)).join(''):'';
  for(const input of $$('form input[type=month]'))if(!input.value)input.value=$('#end').value;
  if(summary.missing.length)notice(`Sem tarifa ou fator anterior para: ${summary.missing.join(', ')}. A economia e as emissões desses meses não foram contabilizadas.`,true);
}
function readForm(id){return Object.fromEntries(new FormData($(id)));}
function monthRequired(month){if(!KPI.validMonth(month))throw Error('Informe uma competência válida entre 1900 e 2200.');}
async function resizePhoto(file){
  if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('Use fotos JPEG, PNG ou WebP.');
  if(file.size>20*1024*1024)throw Error('Cada foto deve ter no máximo 20 MB.');
  const bitmap=await createImageBitmap(file),scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
  const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
  canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();return canvas.toDataURL('image/jpeg',.82);
}
async function init(){
  data=structuredClone(window.KPI_SEED);
  try{database=await openDatabase();const saved=await readDatabase();if(saved)data=KPI.validate(saved);else await persist(data);$('#storage-status').textContent='● Dados salvos neste navegador';}
  catch(error){notice(`Não foi possível abrir os dados locais: ${error.message} Use um navegador com armazenamento habilitado.`,true);$('#storage-status').textContent='Armazenamento indisponível';}
  render();
  $$('.nav').forEach(button=>button.onclick=()=>setTab(button.dataset.tab));
  for(const id of ['start','end','group'])$('#'+id).onchange=()=>{if(!KPI.validMonth($('#start').value)||!KPI.validMonth($('#end').value)){notice('Selecione competências válidas.',true);return;}render();};
  $('#import').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>30*1024*1024)throw Error('A planilha deve ter no máximo 30 MB.');const workbook=XLSX.read(await file.arrayBuffer(),{type:'array',cellDates:true});await change(next=>{const result=KPI.importWorkbook(next,workbook,XLSX);Object.assign(next,result.data);$('#start').value='';$('#end').value='';},'Planilha importada. Leituras da mesma unidade, mês e tipo foram atualizadas.');}catch(error){notice('Não foi possível importar: '+error.message,true);}event.target.value='';};
  $('#backup').onclick=async()=>{await saveQueue;const backup=structuredClone(data);backup.notes=$('#notes').value;download(JSON.stringify(backup,null,2),`backup-solar-${new Date().toISOString().slice(0,10)}.json`,'application/json');};
  $('#restore').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>100*1024*1024)throw Error('Backup maior que 100 MB.');const backup=KPI.validate(JSON.parse(await file.text()));if(confirm('Restaurar este backup substitui os dados deste navegador. Você já guardou uma cópia dos dados atuais?'))await change(next=>{Object.keys(next).forEach(k=>delete next[k]);Object.assign(next,backup);$('#start').value='';$('#end').value='';},'Backup restaurado.');}catch(error){notice(error.message,true);}event.target.value='';};
  $('#reading-form').onsubmit=event=>{event.preventDefault();const f=readForm('#reading-form');change(next=>{monthRequired(f.month);const r={unit:Number(f.unit),month:f.month,type:f.type,value:Number(f.value)},index=next.readings.findIndex(x=>KPI.key(x)===KPI.key(r));if(index<0)next.readings.push(r);else next.readings[index]=r;},'Leitura salva. Ajuste o período acima se necessário.');};
  $('#param-form').onsubmit=event=>{event.preventDefault();const f=readForm('#param-form');change(next=>{monthRequired(f.month);next.params[f.month]={tariff:Number(f.tariff),factor:Number(f.factor)};},'Parâmetros salvos e indicadores recalculados.');};
  $('#param-form input[name=month]').onchange=event=>{const p=data.params[event.target.value],f=$('#param-form');f.elements.tariff.value=p?.tariff??'';f.elements.factor.value=p?.factor??'';};
  $('#edit-unit').onchange=fillUnitForm;
  $('#unit-form').onsubmit=event=>{event.preventDefault();const f=readForm('#unit-form');change(next=>{const name=f.name.trim(),group=f.group.trim();if(!name||!group)throw Error('Preencha nome e grupo.');if(next.units.some(u=>u.id!==Number(f.id)&&KPI.norm(u.name)===KPI.norm(name)))throw Error('Já existe uma unidade com esse nome.');const old=next.units.find(u=>u.id===Number(f.id)),fields={name,group,capacity:Number(f.capacity),area:Number(f.area),panel:f.panel==='on'};if(old){if(old.name!==name&&!old.aliases.includes(old.name))old.aliases.push(old.name);Object.assign(old,fields);}else next.units.push({id:Math.max(0,...next.units.map(u=>u.id))+1,...fields,aliases:[]});},'Unidade salva.');};
  $('#save-notes').onclick=()=>{const notes=$('#notes').value;change(next=>next.notes=notes,'Observações salvas.');};
  $('#photo-form').onsubmit=async event=>{event.preventDefault();const form=$('#photo-form'),f=readForm('#photo-form'),files=[...form.elements.files.files];if(files.length>20){notice('Adicione até 20 fotos por vez.',true);return;}const button=form.querySelector('button');button.disabled=true;try{const photos=[];for(const file of files)photos.push({id:crypto.randomUUID(),unit:Number(f.unit),month:f.month,caption:f.caption,src:await resizePhoto(file)});await change(next=>{monthRequired(f.month);next.photos.push(...photos);},'Fotos salvas. Elas aparecerão no relatório do período correspondente.');}catch(error){notice(error.message,true);}finally{button.disabled=false;}};
  $('#photo-gallery').onclick=event=>{const id=event.target.closest('[data-remove-photo]')?.dataset.removePhoto;if(id&&confirm('Remover esta foto do armazenamento local?'))change(next=>next.photos=next.photos.filter(p=>p.id!==id),'Foto removida.');};
  $('#print').onclick=()=>{if($('#start').value>$('#end').value)return notice('Corrija o intervalo antes de imprimir.',true);$('.notes').dataset.notes=$('#notes').value||'Sem observações registradas.';setTab('overview');notice('Na janela de impressão, escolha “Salvar como PDF”.');window.print();};
  $('#csv').onclick=()=>{const rows=[['Unidade','Grupo','Gerada (kWh)','Perdida (kWh)','Economia (R$)','Emissoes evitadas (tCO2)'],...summary.units.map(u=>[u.name,u.group,num(u.generated,3),num(u.lost,3),num(u.savings,2),num(u.emissions,4)])];const csv=rows.map(row=>row.map(v=>'"'+String(v).replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"').join(';')).join('\r\n');download('\ufeff'+csv,'indicadores-solares.csv','text/csv;charset=utf-8');};
}
init().catch(error=>notice('Falha ao abrir o painel: '+error.message,true));
