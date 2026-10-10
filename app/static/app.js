const el=id=>document.getElementById(id);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(s){el('message').textContent=s;el('message').style.display='block';setTimeout(()=>el('message').style.display='none',6000)}
async function api(url,data){const options=data instanceof FormData?{method:'POST',body:data}:data!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{};const r=await fetch(url,options);const result=await r.json();if(!r.ok)throw Error(result.error||result.detail||r.statusText);return result}
async function diagnostics(){el('diagnostics').textContent='Checking…';el('diagnostics').textContent=JSON.stringify(await api('/api/settings/diagnostics'),null,2)}

const root=el('job');
if(root){
  const job=root.dataset.job,base='/api/jobs/'+job;
  let current=null,signature='',cornerSource=null,corners=[],savingCorners=false;
  const picture=new Image();
  const labels={public:'Public patrons',group:'User group + coaches',dry:'Dry / spectators'};
  const terminal=new Set(['succeeded','failed','needs_review','superseded','skipped']);
  async function refresh(){try{current=await api(base);render(current)}catch(e){toast(e.message)}}

  function render(j){
    const tasks=j.tasks.filter(t=>!['skipped','superseded'].includes(t.state));
    const finished=tasks.filter(t=>terminal.has(t.state)).length;
    const active=tasks.find(t=>t.state==='in_flight');
    const waiting=j.sources.filter(s=>s.normalized&&((!s.geometry&&s.state==='pending')||j.issues.some(i=>i.source_id===s.id&&i.kind==='geometry')));
    const busy=j.sources.some(s=>['pending','processing'].includes(s.state));
    let state=active||busy?'Reading photos…':waiting.length?'Waiting for table corners':j.issues.length?'Ready for image fixes':'Processing complete';
    if(j.state==='paused')state='Processing paused';
    if(j.state==='waiting_for_ollama')state='Waiting for the OCR server';
    el('progress').innerHTML=`<strong>${escape(state)}</strong><p>${finished} of ${tasks.length} reading steps complete${active?` · ${escape(j.sources.find(s=>s.id===active.source_id)?.filename||'')}`:''}${busy&&j.eta_seconds?` · About ${Math.max(1,Math.round(j.eta_seconds/60))} minutes remaining`:''}</p>`;
    el('bar').value=tasks.length?finished/tasks.length*100:busy||waiting.length?0:100;
    el('diagnostic').textContent=j.diagnostic||'';
    el('progress-recovery').innerHTML=['paused','cancelled'].includes(j.state)?'<button data-action="resume">Continue processing</button>':'';
    el('corner-summary').textContent=waiting.length?`${j.sources.length-waiting.length} of ${j.sources.length} images ready. Mark the next image below.`:'All image tables are ready.';
    el('corner-editor').hidden=!waiting.length;
    const next=waiting[0];
    if(next&&next.id!==cornerSource&&!savingCorners){
      cornerSource=next.id;corners=[];
      el('corner-filename').textContent=next.filename;
      el('corner-status').textContent='Loading image…';
      picture.onload=draw;picture.onerror=()=>{el('corner-status').textContent='This image could not be displayed.'};
      picture.src='/files/source/'+next.id;
    }
    if(!next&&!savingCorners)cornerSource=null;
    const latest=j.exports[0];
    el('exports').innerHTML=latest?`${latest.revision<j.revision?'<p>Updating the workbook after your changes…</p>':''}<a class="download" href="/files/export/${latest.id}">Download latest workbook (.xlsx)</a>`:'<p>Your download will appear here when processing finishes.</p>';
    const sig=JSON.stringify([j.revision,j.issues.map(i=>i.id),j.sources.map(s=>[s.id,s.state,s.version])]);
    if(sig===signature)return;
    if(el('issues').contains(document.activeElement))return;
    signature=sig;
    const groups=new Map();
    for(const i of j.issues){
      if(i.kind==='geometry'&&j.sources.find(s=>s.id===i.source_id)?.normalized)continue;
      const cell=j.cells.find(c=>c.key===i.cell_key);
      const observations=cell?JSON.parse(cell.provenance||'[]'):[];
      const sourceId=i.source_id||observations.find(o=>o.source)?.source;
      if(!groups.has(sourceId))groups.set(sourceId,{source:j.sources.find(s=>s.id===sourceId),issues:[]});
      groups.get(sourceId).issues.push({issue:i,cell});
    }
    el('issues').innerHTML=[...groups.values()].map(({source,issues})=>{
      const fields=issues.filter(x=>x.cell).map(({issue,cell})=>`<div class="fix-field"><label for="value-${issue.id}">${escape(cell.date)} · ${escape(cell.time)} · ${escape(labels[cell.column_name]||cell.column_name)}</label><div class="fix-input"><input id="value-${issue.id}" type="number" min="0" step="1" placeholder="Count" value="${cell.value??''}"><label class="blank-choice"><input id="blank-${issue.id}" type="checkbox"> Leave blank</label></div></div>`).join('');
      const date=issues.find(x=>x.issue.kind==='date');
      const sourceIssue=issues.some(x=>!x.cell&&x.issue.kind!=='date');
      return `<article class="fix-image" data-fix-source="${source?.id||''}"><h3>${escape(source?.filename||'Image to check')}</h3>${source?.normalized?`<img class="fix-photo" loading="lazy" src="/files/source/${source.id}" alt="Image with counts to fix">`:'<p>This image could not be read.</p>'}${fields}${date?`<label>Date for this image<input type="date" id="date-${source.id}" value="${escape(source.assigned_date||'')}"></label>`:''}${fields||date?`<button data-save-image="${source?.id||''}">Save corrections</button>`:''}${sourceIssue?`<p>This image could not be fully processed.</p>${source?.normalized?`<button data-retry-image="${source.id}">Try image again</button>`:''}<button class="secondary" data-skip-image="${source?.id||''}">Skip this image</button>`:''}</article>`;
    }).join('')||`<p>${busy?'Images needing a fix will appear here.':waiting.length?'Mark the table corners above to begin.':'No images need fixing.'}</p>`;
  }

  function draw(){
    const c=el('corner-canvas');c.width=picture.width;c.height=picture.height;
    const ctx=c.getContext('2d');ctx.drawImage(picture,0,0);ctx.strokeStyle='#e43c25';ctx.fillStyle='#e43c25';ctx.lineWidth=4;ctx.font='bold 24px system-ui';
    corners.forEach(([x,y],i)=>{ctx.beginPath();ctx.arc(x,y,9,0,2*Math.PI);ctx.stroke();ctx.fillText(String(i+1),x+14,y-10)});
    el('corner-status').textContent=savingCorners?'Saving corners…':`${corners.length} of 4 corners selected${corners.length<4?' · Next: '+['top left','top right','bottom right','bottom left'][corners.length]:''}`;
  }
  el('corner-canvas').onclick=async e=>{
    if(savingCorners||corners.length>=4||!cornerSource||!picture.complete)return;
    const r=e.target.getBoundingClientRect();corners.push([(e.clientX-r.left)*picture.width/r.width,(e.clientY-r.top)*picture.height/r.height]);draw();
    if(corners.length!==4)return;
    savingCorners=true;draw();
    try{
      await api(base+'/sources/'+cornerSource,{geometry:[{section:'auto',corners}],reviewer:'operator'});
      savingCorners=false;cornerSource=null;await refresh();
    }catch(err){savingCorners=false;el('corner-status').textContent=err.message+' Click “Start corners again” to retry.';toast(err.message)}
  };
  el('clear-corners').onclick=()=>{if(!savingCorners){corners=[];draw()}};

  root.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b||b.id==='clear-corners')return;
    const sourceId=b.dataset.saveImage??b.dataset.retryImage??b.dataset.skipImage;
    try{
      b.disabled=true;
      if(b.dataset.action)await api(base+'/control/'+b.dataset.action,{});
      if(b.dataset.saveImage!==undefined){
        const relevant=current.issues.filter(i=>i.source_id===sourceId||current.cells.find(c=>c.key===i.cell_key&&JSON.parse(c.provenance||'[]').some(o=>o.source===sourceId)));
        let saved=0;
        for(const i of relevant){
          const input=el('value-'+i.id),blank=el('blank-'+i.id);
          if(input&&(input.value!==''||blank.checked)){
            if(!blank.checked&&(!Number.isSafeInteger(Number(input.value))||Number(input.value)<0))throw Error('Enter a whole number or choose Leave blank.');
            await api(base+'/review/'+i.id,{action:blank.checked?'blank':'value',value:blank.checked?null:Number(input.value),reviewer:'operator'});saved++;
          }
        }
        const date=el('date-'+sourceId);
        if(date?.value){await api(base+'/sources/'+sourceId,{date:date.value,confirm:true,reviewer:'operator'});saved++}
        if(!saved)throw Error('Enter a count, choose Leave blank, or assign the date.');
        toast('Corrections saved. The workbook will update automatically.');
      }
      if(b.dataset.retryImage!==undefined)await api(base+'/sources/'+sourceId+'/reprocess',{});
      if(b.dataset.skipImage!==undefined){
        for(const i of current.issues.filter(i=>i.source_id===sourceId&&!i.cell_key))await api(base+'/review/'+i.id,{action:'acknowledge',reviewer:'operator',note:'Image skipped in review'});
      }
      if(document.activeElement instanceof HTMLElement)document.activeElement.blur();
      signature='';await refresh();
    }catch(err){toast(err.message)}finally{b.disabled=false}
  });
  refresh();setInterval(refresh,5000);
}
