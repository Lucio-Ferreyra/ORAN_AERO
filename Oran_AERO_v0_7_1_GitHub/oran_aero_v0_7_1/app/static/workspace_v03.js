/* Formulario SYNOP: navegación, autoguardado, cálculos, revisión y visor de claves. */
(()=>{
'use strict';
const source=JSON.parse(document.getElementById('initial-state').textContent);
let wwAll={};fetch('/static/ww4677.json').then(r=>r.json()).then(x=>{wwAll=x;const elem=fields.querySelector('.v04-code-description');if(elem)elem.textContent=wwAll[values.ww]||'Ingresá el código ww.';}).catch(()=>{});
// API requests stay JSON; expired browser sessions return to the login form.
async function synopRequest(url, options){
 const response = await fetch(url, options);
 if(response.status === 401){
  window.location.assign('/login');
  throw new Error('La sesión terminó. Volvé a iniciar sesión.');
 }
 return response;
}
let state=source, values={...source.values}, step=Math.max(0,Math.min(11,source.step||0)), busy=false;
let changeVersion=0, savedVersion=0, saveTimer=null, savingPromise=null;
const $=id=>document.getElementById(id), fields=$('step-fields'), ref=$('reference');
// Catálogo de campos; las pantallas visibles dependen de los datos y de la hora UTC.
const field=(key,label,kind='number',help='',opts=null)=>({key,label,kind,help,opts});
const cloudLevels = [['ch', 'altas', '0509'], ['cm', 'medias', '0515'], ['cl', 'bajas', '0513']];
const genusOptions = [
 ['','Seleccionar'], ...['Cirrus','Cirrocumulus','Cirrostratus','Altocumulus',
 'Altostratus','Nimbostratus','Stratocumulus','Stratus','Cumulus',
 'Cumulonimbus'].map((name,index)=>[String(index),name])
];
const codes = window.OranSynopCodes;
const maxCodeLength = {ww:2,visibility_coarse:2,w1:1,w2:1,tendency_a:1,plafond:1,cloud_total:1,wind_dd:2,wind_force:2};
const descriptionSource = {
 ch_form: codes.cloud.ch, cm_form: codes.cloud.cm, cl_form: codes.cloud.cl,
 soil_state: codes.soil, w1: codes.past, w2: codes.past, tendency_a: codes.tendency
};
const displayCodeDescription = (key,value) => {
 const description=descriptionSource[key];
 if(!description)return;
 const target=fields.querySelector(`[data-description-for="${key}"]`);
 if(target)target.textContent=description[String(value)] || 'Seleccioná un código para ver su descripción.';
};
const observationHourUTC=()=>new Date(state.time_utc).getUTCHours();
const precipitationHours = new Set([0,6,12,18]);
const cloudFields = [
 field('cloud_total','Total de nubes N','digits','0 a 9; con 0 se completan automáticamente los datos de nubosidad.'),
 ...cloudLevels.flatMap(([id,name,table])=>[
  field(`${id}_form`,`Forma de nubes ${name}`,'choice',`Tabla de Clave ${table}.`,[['','Seleccionar'],...Array.from({length:10},(_,i)=>[String(i),String(i)]),['/','/ · Cielo invisible']]),
  field(`${id}_degree`,`Grado de nubes ${name} (octas)`,'digits','Valor de 0 a 8.')
 ]),
 field('plafond','Plafond / código h','coded-height','Tabla 1600: 0–9 o / si la base es desconocida.'),
 ...cloudLevels.map(([id,name])=>field(`${id}_base`,`Base de nubes ${name} · clave 1677`,'digits','Ingresar código hshs, no metros.')),
 field('direction_cl','Dirección desplazamiento DL','digits','Tabla 0700: 0 si no hay nubes bajas.'),
 field('direction_cm','Dirección desplazamiento DM','digits','Tabla 0700: 0 si no hay nubes medias.'),
 field('direction_ch','Dirección desplazamiento DH','digits','Tabla 0700: 0 si no hay nubes altas.'),
 field('conv_c','Género C para grupo 57','digits','Tabla 0500; solo cuando corresponda.'),
 field('conv_da','Dirección Da para grupo 57','digits','Tabla 0700.'),
 field('conv_ec','Elevación ec para grupo 57','digits','Tabla 1004.'),
 field('layer1_genus','Sección 3 · Primera capa: género C','choice','Tabla 0500.',genusOptions),
 field('layer1_octas','Primera capa: Ns (octavos)','digits','Mínimo 1 octavo.'),
 field('layer1_base','Primera capa: hshs (si difiere de base CL)','digits','Dejar en blanco para reutilizar la base CL.'),
 field('layer2_exists','¿Existe una segunda capa?','choice','Si no, no se pedirán más capas.',[['','Seleccionar'],['no','No'],['yes','Sí']]),
 field('layer2_genus','Segunda capa: género C','choice','Tabla 0500.',genusOptions),
 field('layer2_octas','Segunda capa: Ns (octavos)','digits','Mínimo 3 octavos, salvo cumulonimbus.'),
 field('layer2_base','Segunda capa: hshs','digits','Mayor que la primera.'),
 field('layer3_exists','¿Existe una tercera capa?','choice','Si no, continuar al siguiente paso.',[['','Seleccionar'],['no','No'],['yes','Sí']]),
 field('layer3_genus','Tercera capa: género C','choice','Tabla 0500.',genusOptions),
 field('layer3_octas','Tercera capa: Ns (octavos)','digits','Mínimo 5 octavos, salvo cumulonimbus.'),
 field('layer3_base','Tercera capa: hshs (si difiere de base CH)','digits','Dejar en blanco para reutilizar la base CH.')
];
const cloudObserved = cloudFields.filter(f=>['cloud_total','ch_form','ch_degree','cm_form','cm_degree','cl_form','cl_degree'].includes(f.key));
const cloudBases = cloudFields.filter(f=>['plafond','ch_base','cm_base','cl_base','direction_cl','direction_cm','direction_ch','conv_c','conv_da','conv_ec'].includes(f.key));
const cloudLayers = cloudFields.filter(f=>f.key.startsWith('layer'));
const ashRequired=()=>['04','06','07','08','09'].includes(String(values.ww||'').padStart(2,'0'));
const hasClouds=()=>!!values.cloud_total&&!['0','9','/'].includes(String(values.cloud_total));
// Organización de pantallas. No altera las reglas de los grupos SYNOP.
const screens = [
 {id:'dry',title:'Termómetro seco y presión',fields:[
  field('ts','Termómetro seco TS (°C)','decimal','Lectura directa del termómetro seco.'),
  field('pressure_hpa','Presión de estación (hPa)','decimal','Valor observado, no QFF ni QNH.'),
  field('ts_12h_manual','TS de 12 h anteriores, cuando falte en el historial','decimal','Si el sistema recupera el dato histórico, se muestra bloqueado.'),
  field('ts_12h_unavailable','No dispongo de TS de 12 h anteriores','choice','Sin dato se codifica 4////.',[['','Seleccionar'],['yes','Dato no disponible']])
 ]},
 {id:'psychrometry',title:'Termómetro húmedo y psicrometría',fields:[
  field('ts_view','Termómetro seco TS (°C) · dato previo','readonly','Lectura directa, no editable aquí.'),
  field('th','Termómetro húmedo TH (°C)','decimal','Lectura directa del instrumento.'),
  field('psychro_table','Tabla psicrométrica (solo TH negativa)','choice','Elegí Tabla I, II o III cuando TH sea negativa.',[['I','Tabla I'],['II','Tabla II'],['III','Tabla III']])
 ]},
 {id:'wind',title:'Viento',fields:[
  field('wind_dd','Dirección SYNOP dd','digits','Código de dos cifras, no grados.'),
  field('wind_unit','Unidad del viento','choice','1 km/h · 2 m/s · 3 Beaufort · 4 nudos.',[['1','km/h'],['2','m/s'],['3','Beaufort'],['4','nudos']]),
  field('wind_force','Fuerza del viento','digits','Beaufort 0 a 12; el resultado se expresa en nudos.')
 ]},
 {id:'phenomena',title:'Fenómenos, visibilidad y suelo',fields:[
  field('ww','Tiempo presente ww','digits','Tabla 4677, códigos 00–99.'),
  field('visibility_coarse','Visibilidad · escala gruesa VV','digits','Ingresar código de 00 a 89; el sistema calcula la escala fina.'),
  field('soil_state','Estado del suelo (solo libreta)','choice','Tabla de Clave 0901; no integra SYNOP.',[['','Seleccionar'],...Array.from({length:10},(_,i)=>[String(i),String(i)])])
 ]},
 {id:'clouds',title:'Nubosidad observada',fields:cloudObserved},
 {id:'cloud-bases',title:'Bases y desplazamiento',when:hasClouds,fields:cloudBases},
 {id:'cloud-layers',title:'Capas de nubes',when:hasClouds,fields:cloudLayers},
 {id:'precipitation',title:'Precipitación',when:()=>precipitationHours.has(observationHourUTC()),fields:[
  field('precip_state','Situación de precipitación','choice','Trazas: seleccionar sí e ingresar 0 mm.',[['','Seleccionar'],['yes','Hubo precipitación'],['no','No hubo precipitación'],['unknown','Datos no disponibles']]),
  field('precip_mm','Precipitación del período (mm)','decimal','El período tR se determina por la hora UTC.')
 ]},
 {id:'past',title:'Tiempo pasado',fields:[
  field('w1','Tiempo pasado W1','digits','Tabla de Clave 4561, código de un dígito.'),
  field('w2','Tiempo pasado W2','digits','Tabla de Clave 4561, código de un dígito.')
 ]},
 {id:'tendency',title:'Tendencia barométrica',fields:[
  field('pressure_3h_unavailable','Disponibilidad de la presión de 3 horas antes','choice','Indicar si se dispone del dato de presión.',[['','Seleccionar'],['no','Dato disponible'],['yes','Dato no disponible']]),
  field('pressure_3h_manual','Presión de 3 horas antes (hPa)','decimal','Se utiliza el dato histórico si está registrado; de lo contrario, ingresarlo.'),
  field('tendency_a','Código de comportamiento de la tendencia (a)','digits','Tabla de Clave 0200; ingresado por el observador.')
 ]},
 {id:'temperatures',title:'Temperaturas máxima y mínima',when:()=>observationHourUTC()===12,fields:[
  field('temp_max','Termómetro de máxima (°C)','decimal','Sección 3, únicamente a las 12 UTC; se aplica la corrección instrumental.'),
  field('temp_min','Termómetro de mínima (°C)','decimal','Sección 3, únicamente a las 12 UTC; se aplica la corrección instrumental.')
 ]},
 {id:'national',title:'Sección 5 · Datos nacionales',when:()=>observationHourUTC()===12||ashRequired(),fields:[
  field('ash_present','¿Hay ceniza volcánica?','choice','Solo cuando ww sea 04, 06, 07, 08 o 09.',[['','Seleccionar'],['yes','Sí, hay ceniza volcánica'],['no','No hay ceniza volcánica']]),
  field('hr_extremes_confirmed','Confirmación de HR máxima/mínima del día civil anterior (HOA)','choice','Revisá los extremos calculados antes de confirmar.',['','no','yes'].map((value,i)=>[value,['Seleccionar','Revisar todavía','Confirmo que los valores son correctos'][i]]))
 ]}
];
const activeSteps=()=>screens.flatMap((screen,index)=>(!screen.when||screen.when())?[index]:[]);
const ensureActive=()=>{if(!activeSteps().includes(step))step=activeSteps().find(i=>i>step)??activeSteps().at(-1);};
const wwDescriptions={'00':'Desarrollo de nubes no observado o no observable','01':'Nubes disipándose o disminuyendo','02':'Estado del cielo sin cambios apreciables','03':'Nubes formándose o desarrollándose','60':'Lluvia débil intermitente','61':'Lluvia débil continua','62':'Lluvia moderada intermitente','63':'Lluvia moderada continua','65':'Lluvia fuerte continua'};
const refText={wind_dd:'Dirección dd: 00 calma; 01–36 direcciones codificadas (decenas de grados).',wind_force:'Beaufort 0–12. Tabla nudos: 0,2,5,8,13,18,24,30,37,44,52,60,64+. La conversión se realiza según la regla del módulo de viento.',cloud_total:'Grado total 0–8. Si N=0 se autocompleta la nubosidad con 0; si N>0, el observador completa los campos.',cl_degree:'Con CL=8, CM y CH se codifican con / en el SYNOP.',cm_degree:'Con CM=8, CH se codifica con /. CL conserva su valor.',precip_mm:'Trazas: confirmar «Hubo precipitación» e ingresar 0 mm → RRR 990. Sin precipitación y sin datos son estados diferentes.',visibility_fine:'Escala fina calculada automáticamente según clave 4377.',visibility_coarse:'VV: el observador ingresa escala gruesa (00–89).',tendency_a:'Clave 0200. a lo ingresa el observador; ppp sale de la diferencia de presión de estación.',plafond:'Clave de altura de la base de nubes; valor ingresado directamente por el observador.',ts_12h_manual:'Si existe TS histórica de 12 h, solo lectura; si no existe, ingreso manual; sin dato, 4////.'};
function render(){
 ensureActive();
 document.querySelectorAll('[data-step]').forEach(x=>{x.hidden=!activeSteps().includes(+x.dataset.step);x.classList.toggle('selected',+x.dataset.step===step);});
 $('step-title').textContent=screens[step].title;
 fields.replaceChildren();
 for(const f of screens[step].fields){
  const label=document.createElement('label');label.textContent=f.label+(['ww','w1','w2'].includes(f.key)?' *':''); label.className='v03-field';
  if(['conv_c','conv_da','conv_ec'].includes(f.key) && !(hasClouds() && (['2','3','9'].includes(values.cl_form)||values.cm_form==='4')))continue;
  if(f.key==='ash_present'&&!ashRequired())continue;
  if(f.key==='hr_extremes_confirmed'&&!(state.derived?.hr_previous_day_hoa?.max && state.derived?.hr_previous_day_hoa?.min))continue;
  let input;
  if(f.kind==='choice'){
   input=document.createElement('select');for(const [v,t] of f.opts){const op=document.createElement('option');op.value=v;op.textContent=t;input.append(op)}
  }else{input=document.createElement('input');input.type='text';input.inputMode=f.kind==='decimal'?'decimal':f.kind==='coded-height'?'text':'numeric';input.autocomplete='off';if(maxCodeLength[f.key])input.maxLength=maxCodeLength[f.key];}
  input.name=f.key;input.value=f.key==='ts_view'?(values.ts??''):(values[f.key]??'');
  // La obligatoriedad se verifica también al confirmar el SYNOP en el servidor.
  if(['ww','w1','w2'].includes(f.key)){input.required=true;input.setAttribute('aria-required','true');}
  if(f.key==='ts_view')input.disabled=true;
  if(f.key.startsWith('layer2_')&&f.key!=='layer2_exists'&&values.layer2_exists!=='yes'){input.disabled=true;label.hidden=true;}
  if(f.key==='layer3_exists'&&values.layer2_exists!=='yes'){input.disabled=true;label.hidden=true;}
  if(f.key.startsWith('layer3_')&&f.key!=='layer3_exists'&&(values.layer2_exists!=='yes'||values.layer3_exists!=='yes')){input.disabled=true;label.hidden=true;}

  if(f.key==='psychro_table' && !(Number(String(values.th??'').replace(',','.'))<0))input.disabled=true;
  if(f.key==='ts_12h_manual'&&state.historical_ts12!==null){input.value=state.historical_ts12;input.disabled=true;}
  if(f.key==='pressure_3h_manual'&&state.historical_p3_found){input.value='Dato histórico recuperado';input.disabled=true;}
  if(f.key==='pressure_3h_manual' && values.pressure_3h_unavailable==='yes')input.disabled=true;
  if(f.key==='tendency_a' && values.pressure_3h_unavailable==='yes')input.disabled=true;
  for(const id of ['ch','cm','cl']){
   if(f.key===id+'_degree'||f.key===id+'_base') {const absent=values[id+'_form']==='0'||values.cloud_total==='0';if(absent){input.value='0';input.disabled=true;}if(values[id+'_form']==='/'){input.value='/';input.disabled=true;}}
   if(f.key==='direction_'+id){const form=values[id+'_form'];if(form==='0'||values.cloud_total==='0'){input.value='0';input.disabled=true;}else if(form==='/'){input.value='/';input.disabled=true;}}
  }
  if(f.key==='ts_12h_unavailable' && values.ts_12h_manual)input.disabled=true;
  if(['precip_mm'].includes(f.key)&&values.precip_state!=='yes')input.disabled=true;
  const instrumentFor={ts:'ts',th:'th',pressure_hpa:'pressure',wind_dd:'wind',wind_unit:'wind',wind_force:'wind',temp_max:'temp_max',temp_min:'temp_min'}[f.key];
  const inst=instrumentFor && state.instruments?.[instrumentFor];
  if(inst?.status==='fuera_servicio'){input.disabled=true;noteWarning(label,inst.name+' fuera de servicio: campo bloqueado.');}
  if(f.key==='visibility_coarse')input.placeholder='Código VV (00–89)';
  const note=document.createElement('small');note.textContent=f.help;
  label.append(input,note);fields.append(label);
  if(descriptionSource[f.key]){const desc=document.createElement('strong');desc.className='synop-code-description';desc.dataset.descriptionFor=f.key;label.append(desc);displayCodeDescription(f.key,input.value);}
  if(f.key==='ww'){const msg=document.createElement('strong');msg.className='v04-code-description';msg.textContent=wwAll[values.ww]||wwDescriptions[values.ww]||'Consultá la descripción en el PDF de la Clave SYNOP.';label.append(msg);}
  if(f.key==='psychro_table' && input.disabled)label.hidden=true;
  input.addEventListener('focus',()=>{ref.textContent=refText[f.key]||f.help||f.label;});
  input.addEventListener('input',()=>{if(f.kind==='digits')input.value=input.value.replace(/\D/g,'');if(f.kind==='coded-height')input.value=input.value.replace(/[^0-9/]/g,'').slice(0,1);if(f.kind==='decimal')input.value=input.value.replace(/[^0-9.,-]/g,'');if(f.kind!=='choice')onInput(f.key,input.value);});
  if(f.kind==='choice')input.addEventListener('change',()=>onInput(f.key,input.value));
 }

 $('previous').disabled=step===0;
 $('next').textContent=step===activeSteps().at(-1)?'Fin de pantallas':'Siguiente →';
 $('next').disabled=step===activeSteps().at(-1);
 renderDerived();
 // La revisión del mensaje se muestra únicamente tras la confirmación de finalización.
}
function renderDerived(){
 $('derived').replaceChildren();
 const d=state.derived||{};
 const derivedByScreen={dry:{mmhg:'Presión estación mmHg',qnh_hpa:'QNH (hPa)',qff_hpa:'QFF (hPa)'},psychrometry:{dew_point_c:'Punto de rocío (°C)',vapor_hpa:'Tensión de vapor (hPa)',relative_humidity_pct:'Humedad relativa (%)'},wind:{wind_kt:'Viento en nudos'},phenomena:{visibility_fine:'Escala fina calculada'},precipitation:{precip_24h_mm:'Acumulado de 24 horas (mm)',precip_period:'Período UTC'},tendency:{pressure_tendency_hpa:'Variación de presión en 3 h (hPa)'},national:{qnh_hpa:'QNH (hPa)'}};
 const shown=derivedByScreen[screens[step].id]||{};
 for(const [key,title] of Object.entries(shown))if(d[key]!==undefined&&d[key]!==null){const p=document.createElement('p');p.textContent=`${title}: ${d[key]}`;$('derived').append(p);}
 if(screens[step].id==='national' && state.derived?.hr_previous_day_hoa){
  const h=state.derived.hr_previous_day_hoa;
  const note=document.createElement('p');note.textContent=h.max&&h.min?`Humedad del día civil anterior (${h.period_hoa} HOA): máxima ${h.max.value} %, mínima ${h.min.value} %. Confirmá estos valores para continuar.`:'Sin extremos de humedad disponibles para el día anterior.';
  $('derived').append(note);
 }
 const issues=[...(state.missing||[]),...(state.warnings||[])];$('issues').replaceChildren();for(const item of issues){const p=document.createElement('p');p.textContent='• '+item;$('issues').append(p);}
}
function noteWarning(label,text){const e=document.createElement('small');e.className='v04-warning';e.textContent=text;label.append(e);}
// Mantiene coherentes los campos dependientes antes del autoguardado.
function onInput(key,value){
 values[key]=value;
 if(key==='ts_12h_manual'&&value)values.ts_12h_unavailable='';
 if(key==='cloud_total'&&value==='0')for(const k of ['cl_form','cm_form','ch_form','cl_degree','cm_degree','ch_degree','cl_base','cm_base','ch_base','direction_cl','direction_cm','direction_ch'])values[k]='0';
 if(key==='cloud_total'&&value==='0')values.plafond='9';
 if(key==='cloud_total'&&value==='9')values.plafond='/';
 if(key==='wind_force'&&value==='0')values.wind_dd='00';
 if(key==='precip_state'&&value!=='yes')values.precip_mm='';
 if(key==='th' && Number(String(value).replace(',','.'))>=0)values.psychro_table='I';
 // El campo ww no vuelve a dibujarse al escribir: solo cambia su descripción.
 if(['cloud_total','precip_state','wind_force','layer2_exists','layer3_exists','pressure_3h_unavailable','ch_form','cm_form','cl_form'].includes(key))render();
 if(key==='ts_12h_manual'){const x=fields.querySelector('[name="ts_12h_unavailable"]');if(x)x.disabled=!!value;}
 if(key==='ww'){const desc=fields.querySelector('.v04-code-description');if(desc)desc.textContent=wwAll[value]||wwDescriptions[value]||'Consultá la descripción en la Clave SYNOP (PDF).';}
 displayCodeDescription(key,value);
 if(key==='th'){const sel=fields.querySelector('[name="psychro_table"]');if(sel){const neg=Number(String(value).replace(',','.'))<0;sel.disabled=!neg;sel.closest('label').hidden=!neg;}}
 scheduleSave();
}
function scheduleSave(immediate=false){
 changeVersion += 1;
 clearTimeout(saveTimer);
 if (immediate) { void save().catch(()=>{}); }
 else saveTimer=setTimeout(()=>{void save().catch(()=>{});},450);
}
/** Saves are serialized. Final review awaits the latest server-calculated result. */
async function save(){
 clearTimeout(saveTimer);
 if(savingPromise){
  try{await savingPromise;}catch(_error) { /* save status has details */ }
  if(savedVersion>=changeVersion) return state;
 }
 if(savedVersion>=changeVersion) return state;
 const version=changeVersion;
 const payload={observation_id:source.observation_id,values:{...values,_step:step,_ui_flow_version:'2'}};
 $('save-status').textContent='Guardando borrador…';
 const operation=(async()=>{
  const res=await synopRequest('/api/synop/autoguardado',{
   method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
  });
  if(!res.ok){
   let detail='Error '+res.status;
   try{const body=await res.json();detail=body.detail||detail;}catch(_){}
   throw Error(detail);
  }
  const latest=await res.json();
  state=latest;
  savedVersion=version;
  // Do not redraw input elements on save: that would discard focus and unfinished typing.
  renderDerived();
  $('save-status').textContent='Borrador guardado automáticamente';
  return latest;
 })();
 savingPromise=operation;
 try{await operation;}catch(error){
  $('save-status').textContent='No se pudo guardar: '+error.message;
  throw error;
 }finally{if(savingPromise===operation)savingPromise=null;}
 if(savedVersion<changeVersion) return save();
 return state;
}
// Recalcula el informe y muestra su revisión solo al finalizar la carga.
async function openFinalReview(){
 if(busy)return;
 const accepted=await askDialog('Confirmar la carga','¿Finalizaste la carga de datos y querés revisar el informe SYNOP generado?','Revisar SYNOP');
 if(!accepted)return;
 busy=true;
 $('finalize').disabled=true;
 try{
  // Always flush unsaved typing before requesting the final display.
  await save();
  const res=await synopRequest('/api/synop/draft',{cache:'no-store'});
  if(!res.ok)throw Error('No fue posible obtener el informe actualizado ('+res.status+').');
  const reviewed=await res.json();
  state=reviewed;
  $('review-report').hidden=false;
  $('message').textContent=reviewed.message;
  const issues=$('review-issues');issues.replaceChildren();
  for(const line of [...(reviewed.missing||[]),...(reviewed.warnings||[])]){
   const p=document.createElement('p');p.textContent='• '+line;issues.append(p);
  }
  $('review-report').scrollIntoView({behavior:'smooth'});
 }catch(error){
  $('save-status').textContent='No se puede revisar el informe: '+error.message;
  await askDialog('No se pudo completar','Revisá el error de guardado antes de continuar.','Entendido',false);
 }finally{busy=false;$('finalize').disabled=false;}
}
 document.querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',()=>{if(activeSteps().includes(+b.dataset.step)){step=+b.dataset.step;render();scheduleSave(true)}}));
 $('previous').addEventListener('click',()=>{step=activeSteps().filter(i=>i<step).at(-1)??0;render();scheduleSave(true)});
 $('next').addEventListener('click',()=>{step=activeSteps().find(i=>i>step)??step;render();scheduleSave(true)});
 $('new-observation').addEventListener('click',async()=>{
  if(!await askDialog('Nueva observación','¿Descartar el borrador actual e iniciar otra observación?','Descartar e iniciar'))return;
  const payload={discard_confirmed:true};
  const r=await synopRequest('/api/synop/nueva',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(r.ok)location.reload();else await askDialog('No se pudo iniciar','No se pudo iniciar una nueva observación.','Entendido',false);
 });
 $('finalize').addEventListener('click',openFinalReview);
 $('return-edit').addEventListener('click',()=>{$('review-report').hidden=true;document.querySelector('.v03-entry').scrollIntoView({behavior:'smooth'});});
 $('review-save').addEventListener('click',async()=>{
   if(!await askDialog('Guardar informe SYNOP','¿Confirmás que los datos del mensaje revisado son correctos? Se guardará una nueva versión si se trata de una corrección.','Guardar informe'))return;
   try{
     await save();
     const res=await synopRequest('/api/synop/finalizar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({observation_id:source.observation_id,confirmed:true})});
     const data=await res.json();
     if(!res.ok){const issues=data.detail?.missing||[];throw Error((data.detail?.message||data.detail||'Error al guardar')+(issues.length?' · '+issues.join(' · '):''));}
     location.href=data.redirect;
   }catch(error){$('save-status').textContent='No se pudo guardar: '+error.message;await askDialog('Revisar datos',error.message,'Entendido',false);}
 });
// Confirmaciones modales con el estilo de la aplicación.
function askDialog(title,message,okText='Confirmar',cancel=true){return new Promise(resolve=>{const modal=$('confirm-modal');$('confirm-title').textContent=title;$('confirm-text').textContent=message;$('confirm-ok').textContent=okText;$('confirm-cancel').hidden=!cancel;modal.hidden=false;const done=answer=>{modal.close();modal.hidden=true;$('confirm-ok').removeEventListener('click',yes);$('confirm-cancel').removeEventListener('click',no);modal.removeEventListener('cancel',esc);resolve(answer);};const yes=()=>done(true),no=()=>done(false),esc=e=>{e.preventDefault();done(false)};$('confirm-ok').addEventListener('click',yes);$('confirm-cancel').addEventListener('click',no);modal.addEventListener('cancel',esc);modal.showModal();$('confirm-ok').focus();});}
 const pdfTitles={
  'clave_synop_smn_2022.pdf':'Clave SYNOP — SMN 2022',
  'libreta_smn_2022.pdf':'Llenado de Libreta Meteorológica — 2022'
 };
 function selectPdf(filename){
  if(!Object.prototype.hasOwnProperty.call(pdfTitles,filename))return;
  const url='/documentos/'+encodeURIComponent(filename);
  $('pdf-select').value=filename;
  $('pdf-frame').src=url+'#toolbar=1&view=FitH';
  $('pdf-frame').title=pdfTitles[filename];
  $('pdf-open').href=url;
  $('pdf-name').textContent=pdfTitles[filename];
  document.querySelectorAll('[data-pdf]').forEach(button=>{
   const active=button.dataset.pdf===filename;
   button.classList.toggle('is-active',active);
   button.setAttribute('aria-pressed',String(active));
  });
 }
 $('pdf-select').addEventListener('change',e=>selectPdf(e.target.value));
 document.querySelectorAll('[data-pdf]').forEach(button=>button.addEventListener('click',()=>selectPdf(button.dataset.pdf)));
 const pdfPanel=$('pdf-panel');
 function expandPdf(yes){
  pdfPanel.classList.toggle('v04-pdf-fullscreen',yes);
  document.body.classList.toggle('v04-pdf-modal',yes);
  $('pdf-expand').hidden=yes;
  $('pdf-close').hidden=!yes;
  $('pdf-expand').setAttribute('aria-expanded',String(yes));
  if(yes)$('pdf-close').focus();else $('pdf-expand').focus();
 }
 $('pdf-expand').addEventListener('click',()=>expandPdf(true));
 $('pdf-close').addEventListener('click',()=>expandPdf(false));
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&pdfPanel.classList.contains('v04-pdf-fullscreen'))expandPdf(false)});
 render();
 // Un borrador antiguo nunca cambia de fecha silenciosamente: el observador
 // decide si quiere conservarlo o iniciar el horario UTC siguiente.
 if(source.stale_draft){
  const formatUtc=instant=>new Intl.DateTimeFormat('es-AR',{
   timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric',
   hour:'2-digit',minute:'2-digit',hourCycle:'h23'
  }).format(new Date(instant));
  askDialog('Borrador de otra hora',
   `Este borrador es del ${formatUtc(source.time_utc)} UTC. El próximo horario es ${formatUtc(source.proposed_next_time_utc)} UTC. ¿Querés descartar el borrador anterior e iniciar el siguiente?`,
   'Iniciar siguiente SYNOP').then(async accepted=>{
     if(!accepted)return;
     try{
       const response=await synopRequest('/api/synop/nueva',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({discard_confirmed:true})
       });
       if(!response.ok)throw new Error('No fue posible iniciar el siguiente SYNOP.');
       location.reload();
     }catch(error){$('save-status').textContent=error.message;}
   });
 }
})();
