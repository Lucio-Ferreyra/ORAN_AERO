/* Administración de estación, instrumental, personal y contraseñas. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
function filterList(searchId,checkId,containerId){
 const input=$(searchId),check=$(checkId),container=$(containerId);if(!input||!container)return;
 function refresh(){const term=input.value.toLocaleLowerCase().trim();container.querySelectorAll('.catalog-row').forEach(row=>{
  row.hidden=!row.dataset.search.includes(term)|| (!!check&&!check.checked&&row.dataset.status==='fuera_servicio');
 });}input.addEventListener('input',refresh);if(check)check.addEventListener('change',refresh);refresh();
}
filterList('instrument-search','include-archived','instruments-list');
filterList('person-search','include-inactive','person-list');
const stationId=$('station-identifier'),stationBlock=$('station-block'),stationNumber=$('station-number');
if(stationId&&stationBlock&&stationNumber){
 stationId.addEventListener('input',()=>{
   const digits=stationId.value.replace(/\D/g,'').slice(0,5);stationId.value=digits;
   if(digits.length===5){stationBlock.value=digits.slice(0,2);stationNumber.value=digits.slice(2);}
 });
 const sync=()=>{if(/^\d{2}$/.test(stationBlock.value)&&/^\d{3}$/.test(stationNumber.value))stationId.value=stationBlock.value+stationNumber.value;};
 stationBlock.addEventListener('input',sync);stationNumber.addEventListener('input',sync);
}
const windMethod=$('wind-method'),windIw=$('wind-iw');
if(windMethod&&windIw){
 function options(){const estimated=windMethod.value==='estimado',previous=windIw.value||windIw.dataset.selected;
  windIw.replaceChildren();
  for(const [val,title] of (estimated?[['0','0 · viento estimado en m/s'],['3','3 · viento estimado en nudos']]:[['1','1 · anemómetro en m/s'],['4','4 · anemómetro en nudos']])){
   const op=document.createElement('option');op.value=val;op.textContent=title;windIw.append(op);
  }
  if([...windIw.options].some(op=>op.value===previous))windIw.value=previous;
 }
 windMethod.addEventListener('change',options);options();
}
window.openInstrument=function(data){const dialog=$('instrument-edit');if(!dialog)return;
 $('instrument-title').textContent=data?'Modificar instrumento':'Cargar instrumento';
 const pairs={'in-id':'id','in-name':'name','in-brand':'brand','in-type':'instrument_type','in-number':'serial_number',
 'in-correction-mode':'correction_mode','in-correction-value':'correction_value','in-status':'status',
 'in-physical':'physical_state','in-patrimony':'patrimony_number'};
 for(const [id,key] of Object.entries(pairs)){
  const el=$(id);el.value=data&&data[key]!=null?String(data[key]):({'in-id':'0','in-brand':'S/D','in-type':'ts','in-correction-mode':'SC','in-correction-value':'0','in-status':'en_servicio','in-physical':'Bueno'}[id]||'');
 }
 dialog.showModal();
};
window.openPerson=function(data){const dialog=$('person-edit');if(!dialog)return;
 $('person-title').textContent=data?'Modificar personal':'Cargar personal';
 const pairs={'person-id':'id','person-username':'username','person-name':'full_name','person-role':'role','person-active':'active'};
 for(const [id,key] of Object.entries(pairs)){
  const el=$(id);el.value=data&&data[key]!=null?(key==='active'?(data[key]?'yes':'no'):String(data[key])):({'person-id':'0','person-role':'observador','person-active':'yes'}[id]||'');
 }
 $('person-password').required=!data;$('person-password-wrap').hidden=!!data;
 dialog.showModal();
};
window.openPassword=function(id,own){const dialog=$('password-edit');if(!dialog)return;
 $('password-target').value=id;$('password-current-wrap').hidden=!own;
 $('password-current').required=!!own;$('password-current').value='';$('password-new').value='';
 $('password-title').textContent=own?'Cambiar mi contraseña':'Restablecer contraseña';
 dialog.showModal();
};
})();
