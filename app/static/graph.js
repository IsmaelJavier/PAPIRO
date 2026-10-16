const jobId = location.pathname.split('/').filter(Boolean).pop();
const API = `/api/v1`;
let graphData = null, cy = null, findings = [], entities = [], correlations = [], relationships = [];
let selectedFindingIds = new Set(), selectedEntityIds = new Set(), selectedElement = null;
let hiddenNodeIds = new Set(JSON.parse(localStorage.getItem(`kami:hidden:${jobId}`) || '[]'));
const positionKey = `kami:positions:${jobId}`;
let editingEntityId = null, editingRelationshipId = null;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labelMap = { shared_username:'shared username', shared_email:'shared email', shared_phone:'shared phone number', shared_url:'URL compartida', shared_domain:'shared domain', shared_organization:'shared organization', shared_location:'shared location' };
const identityText = { indeterminado:'Undetermined', pertenece:'Belongs', no_pertenece:'Does not belong' };
const relevanceText = { indeterminado:'Undetermined', relevante:'Relevant', no_relevante:'Not relevant' };
const assessmentText = { indeterminado:'Undetermined', confirmada:'Confirmed', descartada:'Rejected' };
function closeModal(id){ document.getElementById(id).style.display='none'; }
function openModal(id){ document.getElementById(id).style.display='flex'; }
const TOKEN_KEY = 'kami:access-token';
function updateAuthButton(){
  const btn = document.getElementById('authBtn');
  if(btn) btn.textContent = localStorage.getItem(TOKEN_KEY) ? 'Sign out' : 'Sign in';
}
async function api(path, options={}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  if(token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`${API}${path}`, { ...options, headers });
  let data = null; try { data = await r.json(); } catch {}
  if(r.status === 401){
    localStorage.removeItem(TOKEN_KEY);
    updateAuthButton();
    location.replace('/ui');
  }
  if (!r.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : (detail?.message || `HTTP ${r.status}`);
    const error = new Error(message);
    if(detail && typeof detail === 'object') error.details = detail;
    throw error;
  }
  return data;
}
async function submitLogin(event){
  event.preventDefault();
  const button = document.getElementById('loginSubmitBtn');
  const error = document.getElementById('loginError');
  button.disabled = true; error.textContent = '';
  try{
    const response = await fetch(`${API}/auth/login`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        email:document.getElementById('loginEmail').value.trim(),
        password:document.getElementById('loginPassword').value
      })
    });
    let data = null; try{data=await response.json()}catch{}
    if(!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
    localStorage.setItem(TOKEN_KEY,data.access_token);
    document.getElementById('loginPassword').value='';
    closeModal('loginModal'); updateAuthButton(); await loadAll();
  }catch(e){error.textContent=e.message;}
  finally{button.disabled=false;}
}

function showAuthTab(tab){
  const login = tab === 'login';
  document.getElementById('loginForm').hidden = !login;
  document.getElementById('registerForm').hidden = login;
  document.getElementById('authTitle').textContent = login ? 'Sign in' : 'Create account';
  document.getElementById('showLoginTab').classList.toggle('primary', login);
  document.getElementById('showRegisterTab').classList.toggle('primary', !login);
  document.getElementById('showLoginTab').setAttribute('aria-selected', String(login));
  document.getElementById('showRegisterTab').setAttribute('aria-selected', String(!login));
  document.getElementById(login ? 'registerError' : 'loginError').textContent = '';
}
async function submitRegister(event){
  event.preventDefault();
  const button = document.getElementById('registerSubmitBtn');
  const error = document.getElementById('registerError');
  const password = document.getElementById('registerPassword').value;
  const confirmation = document.getElementById('registerPasswordConfirm').value;
  error.textContent = '';
  if(password.length < 12){ error.textContent = 'Password must contain at least 12 characters.'; return; }
  if(password !== confirmation){ error.textContent = 'Passwords do not match.'; return; }
  button.disabled = true;
  try{
    const response = await fetch(`${API}/auth/register`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:document.getElementById('registerEmail').value.trim(),password,global_role:document.getElementById('registerRole').value})
    });
    let data = null; try{data=await response.json()}catch{}
    if(!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
    localStorage.setItem(TOKEN_KEY,data.access_token);
    document.getElementById('registerPassword').value='';
    document.getElementById('registerPasswordConfirm').value='';
    closeModal('loginModal'); updateAuthButton(); await loadAll();
  }catch(e){error.textContent=e.message;}
  finally{button.disabled=false;}
}
function badge(text, cls=''){ return `<span class="badge ${cls}">${esc(text)}</span>`; }
function findingById(id){ return findings.find(f=>f.id===id); }
function entityById(id){ return entities.find(e=>e.id===id); }
function correlationById(id){ return correlations.find(c=>c.id===id); }
function setDetails(html){ document.getElementById('details').innerHTML = html; }
function sourceLink(url){ return url ? `<a href="${esc(url)}" target="_blank" rel="noopener">Open source</a>` : '—'; }

function renderFindings(){
  const source = document.getElementById('sourceFilter').value;
  const q = document.getElementById('findingSearch').value.trim().toLowerCase();
  const list = document.getElementById('findingList');
  const rows = findings.filter(f => {
    const hay = `${f.value} ${f.source} ${f.finding_type} ${f.source_url} ${f.match_reason}`.toLowerCase();
    return (source==='all'||f.source===source) && (!q||hay.includes(q));
  });
  if (!rows.length){ list.innerHTML='<div class="empty">No findings match this filter.</div>'; return; }
  list.innerHTML = rows.map(f => {
    const selected = selectedFindingIds.has(f.id);
    const ic = f.identity_assessment==='pertenece'?'ok':f.identity_assessment==='no_pertenece'?'no':'warn';
    const rc = f.relevance_assessment==='relevante'?'ok':f.relevance_assessment==='no_relevante'?'no':'warn';
    return `<div class="finding ${selected?'selected':''}" data-finding="${esc(f.id)}">
      <input type="checkbox" ${selected?'checked':''} aria-label="Select finding">
      <div class="finding-main">
        <div class="finding-title">${esc(f.value)}</div>
        <div class="finding-meta">${esc(f.source)} · ${esc(f.finding_type)} · evidence strength ${Number(f.evidence_strength).toFixed(2)}</div>
        <div style="margin-top:4px">${badge(identityText[f.identity_assessment]||f.identity_assessment,ic)}${badge(relevanceText[f.relevance_assessment]||f.relevance_assessment,rc)}</div>
      </div>
    </div>`;
  }).join('');
  list.querySelectorAll('.finding').forEach(el => {
    const id=el.dataset.finding;
    el.querySelector('input').addEventListener('change', e => { toggleFinding(id,e.target.checked); });
    el.querySelector('.finding-main').addEventListener('click', e => { if (!e.target.closest('a,button')) toggleFinding(id, !selectedFindingIds.has(id)); });
  });
  updateSelectionUI();
}
function toggleFinding(id, checked){ checked ? selectedFindingIds.add(id) : selectedFindingIds.delete(id); renderFindings(); syncGraphSelection(); }
function updateSelectionUI(){
  const n=selectedFindingIds.size;
  document.getElementById('createEntityBtn').disabled=n===0;
  document.getElementById('selectionHelp').textContent = n ? `${n} finding(s) selected. You can create a candidate entity and associate this evidence in one step.` : 'Select one or more findings to build a candidate profile.';
}
function selectVisible(){ document.querySelectorAll('#findingList .finding').forEach(el=>selectedFindingIds.add(el.dataset.finding)); renderFindings(); syncGraphSelection(); }
function clearSelection(){ selectedFindingIds.clear(); selectedEntityIds.clear(); renderFindings(); renderEntities(); syncGraphSelection(); }

function renderEntities(){
  const list=document.getElementById('entityList');
  if(!entities.length){ list.innerHTML='<div class="empty">There are no candidate profiles yet. Select evidence to create the first one.</div>'; return; }
  list.innerHTML=entities.map(e=>`<div class="entity-card ${selectedEntityIds.has(e.id)?'selected':''}" data-entity="${esc(e.id)}">
    <div class="entity-name">${esc(e.label)}</div>
    <div class="entity-meta">${e.findings.length} associated finding(s) · ${esc(e.entity_type)}</div>
    <div class="entity-actions"><button class="btn small view-entity">View profile</button></div>
  </div>`).join('');
  list.querySelectorAll('.entity-card').forEach(el=>{
    const id=el.dataset.entity;
    el.querySelector('.view-entity').onclick=()=>showEntity(id);
  });
}
function toggleEntitySelection(id){
  if(selectedEntityIds.has(id)) selectedEntityIds.delete(id); else selectedEntityIds.add(id);
  if(selectedEntityIds.size>2){ const arr=[...selectedEntityIds]; selectedEntityIds=new Set(arr.slice(-2)); }
  renderEntities(); syncGraphSelection();
  const selectionButton=document.querySelector('#details [data-entity-selection-button]');
  if(selectionButton&&selectionButton.dataset.entitySelectionButton===id){
    const selected=selectedEntityIds.has(id);
    selectionButton.textContent=selected?'Remove from relationship selection':'Select for relationship';
    selectionButton.setAttribute('aria-pressed',String(selected));
  }
  if(selectedEntityIds.size===2) openRelationshipModal();
}
function syncGraphSelection(){
  if(!cy) return;
  cy.nodes().removeClass('investigator-selected');
  selectedFindingIds.forEach(id=>cy.$(`#finding\\:${CSS.escape(id)}`).addClass('investigator-selected'));
  selectedEntityIds.forEach(id=>cy.$(`#entity\\:${CSS.escape(id)}`).addClass('investigator-selected'));
}

function showFinding(id){
  const f=findingById(id); if(!f) return;
  setDetails(`<div class="detail-title">Finding</div><div class="detail-sub">${esc(f.source)} · ${esc(f.finding_type)}</div>
    <div class="detail-actions"><button class="btn small" onclick="hideNode('finding:${esc(f.id)}')">Hide from graph</button><button class="btn small" onclick="focusNode('finding:${esc(f.id)}')">Center in graph</button></div>
    <div class="detail-actions"><button class="btn small" onclick="assessFinding('${esc(f.id)}','identity_assessment','pertenece')">Belongs to candidate</button><button class="btn small" onclick="assessFinding('${esc(f.id)}','identity_assessment','no_pertenece')">Does not belong</button><button class="btn small" onclick="assessFinding('${esc(f.id)}','identity_assessment','indeterminado')">Undetermined</button></div>
    <div class="detail-actions"><button class="btn small" onclick="assessFinding('${esc(f.id)}','relevance_assessment','relevante')">Relevant</button><button class="btn small" onclick="assessFinding('${esc(f.id)}','relevance_assessment','no_relevante')">Not relevant</button><button class="btn small" onclick="assessFinding('${esc(f.id)}','relevance_assessment','indeterminado')">Undetermined</button></div>
    ${kv('Value',f.value)}${kv('Source',sourceLink(f.source_url),true)}${kv('Identity',identityText[f.identity_assessment])}${kv('Relevance',relevanceText[f.relevance_assessment])}${kv('Evidence strength',Number(f.evidence_strength).toFixed(2))}${kv('Match reason',f.match_reason)}
    <h3 style="margin-top:14px">Indicators</h3>${f.indicators?.map(i=>`<div class="kv"><b>${esc(i.indicator_type)}</b>${esc(i.value)} <span style="color:var(--muted)">(${esc(i.normalized_value)})</span></div>`).join('')||'<div class="empty">No indicators.</div>'}`);
}
function kv(k,v,raw=false){ return `<div class="kv"><b>${esc(k)}</b>${raw?v:esc(v??'—')}</div>`; }
async function assessFinding(id, field, value){
  try { const body={}; body[field]=value; await api(`/findings/${encodeURIComponent(id)}/assessment`,{method:'PATCH',body:JSON.stringify(body)}); await loadAll(); showFinding(id); }
  catch(e){ alert(`Could not update the finding: ${e.message}`); }
}

async function showEntity(id){
  try{
    const p=await api(`/entities/${encodeURIComponent(id)}/profile`);
    setDetails(`<div class="detail-title">${esc(p.label)}</div><div class="detail-sub">Candidate profile · ${esc(p.entity_type)}</div>
      <div class="detail-actions"><button class="btn primary small" type="button" data-entity-selection-button="${esc(id)}" aria-pressed="${selectedEntityIds.has(id)}" onclick="toggleEntitySelection('${esc(id)}')">${selectedEntityIds.has(id)?'Remove from relationship selection':'Select for relationship'}</button><button class="btn small" onclick="openEntityEdit('${esc(id)}')">Edit profile</button><button class="btn small" onclick="hideNode('entity:${esc(id)}')">Hide from graph</button><button class="btn small" onclick="focusNode('entity:${esc(id)}')">Center in graph</button></div>
      ${kv('Description',p.description||'No description')}
      <h3 style="margin-top:14px">Associated evidence (${p.findings.length})</h3>
      ${p.findings.map(f=>`<div class="finding" style="margin-bottom:7px"><div class="finding-main"><div class="finding-title">${esc(f.value)}</div><div class="finding-meta">${esc(f.source)} · ${esc(f.finding_type)}</div></div></div>`).join('')||'<div class="empty">No evidence.</div>'}
      <div class="detail-actions"><button class="btn small" onclick="attachSelectedFindingsToEntity('${esc(id)}')" ${selectedFindingIds.size?'':'disabled'}>Add selection as evidence</button></div>
      <h3 style="margin-top:14px">Derived indicators (${p.indicators.length})</h3>
      ${p.indicators.map(i=>`<div class="kv"><b>${esc(i.indicator_type)}</b>${esc(i.value)}</div>`).join('')||'<div class="empty">No indicators.</div>'}
      <h3 style="margin-top:14px">Relationships (${p.relationships.length})</h3>
      ${p.relationships.map(r=>`<div class="entity-card" style="margin-bottom:7px"><div class="entity-name">${esc(entityById(r.entity_a_id)?.label||r.entity_a_id)} ↔ ${esc(entityById(r.entity_b_id)?.label||r.entity_b_id)}</div><div class="entity-meta">${esc(r.relationship_type)} · ${esc(assessmentText[r.assessment]||r.assessment)}</div><button class="btn small" onclick="showRelationship('${esc(r.id)}')">View relationship</button></div>`).join('')||'<div class="empty">No relationships.</div>'}`);
  }catch(e){ alert(`Could not load the profile: ${e.message}`); }
}
function openEntityEdit(id){ const e=entityById(id); if(!e)return; editingEntityId=id; document.getElementById('editEntityLabel').value=e.label||''; document.getElementById('editEntityDescription').value=e.description||''; openModal('entityEditModal'); }
async function saveEntityEdit(){ if(!editingEntityId)return; const label=document.getElementById('editEntityLabel').value.trim(); if(!label){alert('The working name cannot be empty.');return;} try{ await api(`/entities/${encodeURIComponent(editingEntityId)}`,{method:'PATCH',body:JSON.stringify({label,description:document.getElementById('editEntityDescription').value.trim()||null})}); const id=editingEntityId; closeModal('entityEditModal'); await loadAll(true); showEntity(id); }catch(e){alert(`Could not edit the entity: ${e.message}`);} }
async function attachSelectedFindingsToEntity(id){ if(!selectedFindingIds.size)return; try{ for(const findingId of selectedFindingIds){ await api(`/entities/${encodeURIComponent(id)}/findings`,{method:'POST',body:JSON.stringify({finding_id:findingId,role:'evidencia'})}); } await loadAll(true); showEntity(id); }catch(e){alert(`Could not associate evidence: ${e.message}`);} }
function showRelationship(id){ const r=relationships.find(x=>x.id===id); if(!r)return; const a=entityById(r.entity_a_id), b=entityById(r.entity_b_id); setDetails(`<div class="detail-title">Relationship</div><div class="detail-sub">${esc(a?.label||r.entity_a_id)} ↔ ${esc(b?.label||r.entity_b_id)}</div>
    <div class="detail-actions"><button class="btn small" onclick="openRelationshipEdit('${esc(r.id)}')">Edit relationship</button><button class="btn success small" onclick="assessRelationship('${esc(r.id)}','confirmada')">Confirm</button><button class="btn danger small" onclick="assessRelationship('${esc(r.id)}','descartada')">Reject</button><button class="btn small" onclick="assessRelationship('${esc(r.id)}','indeterminado')">Undetermined</button></div>
    ${kv('Type',r.relationship_type)}${kv('Assessment',assessmentText[r.assessment]||r.assessment)}${kv('Basis',r.basis)}${r.evidence?.length ? `<h3 style="margin-top:14px">Relationship evidence</h3>${r.evidence.map(e=>`<div class="kv"><b>Correlation</b>${esc(e.correlation_id||'')} · findings ${esc(e.finding_a_id||'')} / ${esc(e.finding_b_id||'')}</div>`).join('')}` : ''}`); }
function openRelationshipEdit(id){ const r=relationships.find(x=>x.id===id); if(!r)return; editingRelationshipId=id; document.getElementById('editRelationshipType').value=r.relationship_type||''; document.getElementById('editRelationshipBasis').value=r.basis||''; openModal('relationshipEditModal'); }
async function saveRelationshipEdit(){ if(!editingRelationshipId)return; const type=document.getElementById('editRelationshipType').value.trim(); const basis=document.getElementById('editRelationshipBasis').value.trim(); if(!type||!basis){alert('Relationship type and basis are required.');return;} try{ await api(`/relationships/${encodeURIComponent(editingRelationshipId)}`,{method:'PATCH',body:JSON.stringify({relationship_type:type,basis})}); const id=editingRelationshipId; closeModal('relationshipEditModal'); await loadAll(true); showRelationship(id); }catch(e){alert(`Could not edit the relationship: ${e.message}`);} }
async function assessRelationship(id,value){ try{ await api(`/relationships/${encodeURIComponent(id)}/assessment`,{method:'PATCH',body:JSON.stringify({assessment:value})}); await loadAll(); showRelationship(id); }catch(e){ alert(`Could not assess the relationship: ${e.message}`); } }
function showCorrelation(id){
  const c=correlationById(id); if(!c) return;
  setDetails(`<div class="detail-title">Correlation</div><div class="detail-sub">${esc(labelMap[c.correlation_type]||c.correlation_type)}</div>
    <div class="detail-actions"><button class="btn success small" onclick="assessCorrelation('${esc(c.id)}','confirmada')">Confirm</button><button class="btn danger small" onclick="assessCorrelation('${esc(c.id)}','descartada')">Reject</button><button class="btn small" onclick="assessCorrelation('${esc(c.id)}','indeterminado')">Undetermined</button></div>
    ${kv('Basis',c.basis)}${kv('Assessment',assessmentText[c.assessment]||c.assessment)}${kv('Finding A',findingById(c.finding_a_id)?.value||c.finding_a_id)}${kv('Finding B',findingById(c.finding_b_id)?.value||c.finding_b_id)}${c.evidence?.map(e=>kv(e.indicator_type,e.normalized_value)).join('')||''}`);
}
async function assessCorrelation(id,value){ try{ await api(`/correlations/${encodeURIComponent(id)}/assessment`,{method:'PATCH',body:JSON.stringify({assessment:value})}); await loadAll(); showCorrelation(id); }catch(e){ alert(`Could not assess the correlation: ${e.message}`); } }

function openEntityModal(){
  const ids=[...selectedFindingIds];
  if(!ids.length) return;
  document.getElementById('entityLabel').value=`Candidate ${entities.length+1}`;
  document.getElementById('entityDescription').value='';
  document.getElementById('entitySelectedFindings').innerHTML=ids.map(id=>{const f=findingById(id);return `<div class="selected-item">• ${esc(f?.value||id)} <span style="color:var(--muted)">(${esc(f?.source||'')})</span></div>`}).join('');
  openModal('entityModal');
}
async function saveEntity(){
  const label=document.getElementById('entityLabel').value.trim(); if(!label){alert('Escribe un nombre de trabajo para el candidato.');return;}
  try{ await api(`/jobs/${encodeURIComponent(jobId)}/entities`,{method:'POST',body:JSON.stringify({label,entity_type:'person_candidate',description:document.getElementById('entityDescription').value.trim()||null,finding_ids:[...selectedFindingIds]})}); closeModal('entityModal'); selectedFindingIds.clear(); await loadAll(); }
  catch(e){ alert(`Could not create the entity: ${e.message}`); }
}
function openRelationshipModal(){
  if(selectedEntityIds.size!==2){alert('Select exactly two entities.');return;}
  const [a,b]=[...selectedEntityIds], ea=entityById(a), eb=entityById(b);
  document.getElementById('relationshipEntities').innerHTML=`<b>${esc(ea.label)}</b> ↔ <b>${esc(eb.label)}</b>`;
  const sel=document.getElementById('relationshipCorrelation');
  const eligible=correlations.filter(c=>{
    const fa=entityById(a)?.findings.map(x=>x.finding_id)||[], fb=entityById(b)?.findings.map(x=>x.finding_id)||[];
    return (fa.includes(c.finding_a_id)&&fb.includes(c.finding_b_id))||(fa.includes(c.finding_b_id)&&fb.includes(c.finding_a_id));
  });
  sel.innerHTML='<option value="">No correlation selected</option>'+eligible.map(c=>`<option value="${esc(c.id)}">${esc(labelMap[c.correlation_type]||c.correlation_type)} · ${esc(c.basis)}</option>`).join('');
  document.getElementById('relationshipBasis').value=eligible.length?`Evidence associated with correlation: ${eligible[0].basis}`:'';
  openModal('relationshipModal');
}
async function saveRelationship(){
  const [a,b]=[...selectedEntityIds]; const corr=document.getElementById('relationshipCorrelation').value||null;
  const basis=document.getElementById('relationshipBasis').value.trim(); if(!basis){alert('Describe the observable basis for the relationship.');return;}
  const c=corr?correlationById(corr):null;
  try{ await api(`/jobs/${encodeURIComponent(jobId)}/relationships`,{method:'POST',body:JSON.stringify({entity_a_id:a,entity_b_id:b,relationship_type:document.getElementById('relationshipType').value,basis,assessment:'indeterminado',correlation_id:corr,finding_a_id:c?.finding_a_id||null,finding_b_id:c?.finding_b_id||null})}); closeModal('relationshipModal'); await loadAll(); }
  catch(e){ alert(`Could not create the relationship: ${e.message}`); }
}

function readPositions(){ try{return JSON.parse(localStorage.getItem(positionKey)||'{}')}catch{return {};} }
function setSaveStatus(message){const el=document.getElementById('saveStatus');if(el)el.textContent=message;}
function savePositions(){ if(!cy)return; const positions={}; cy.nodes().forEach(n=>{positions[n.id()]={x:n.position('x'),y:n.position('y')};}); localStorage.setItem(positionKey,JSON.stringify(positions));setSaveStatus('View saved automatically'); }
function persistHidden(){localStorage.setItem(`kami:hidden:${jobId}`,JSON.stringify([...hiddenNodeIds]));setSaveStatus('View saved automatically');}
function hideNode(id){hiddenNodeIds.add(id);persistHidden();applyGraphFilters();}
function showAllHidden(){hiddenNodeIds.clear();persistHidden();applyGraphFilters();}
function focusNode(id){if(!cy)return;hiddenNodeIds.delete(id);persistHidden();applyGraphFilters();const n=cy.getElementById(id);if(n.length){cy.animate({fit:{eles:n,padding:140},duration:250});n.select();}}
function hideSelected(){if(!cy)return;cy.nodes('.investigator-selected').forEach(n=>hiddenNodeIds.add(n.id()));persistHidden();applyGraphFilters();}
function buildGraph(preserve=true){
  const nodes=(graphData.nodes||[]).map(n=>({data:n})), edges=(graphData.edges||[]).map(e=>({data:e}));
  const stored=readPositions(); if(cy){savePositions();cy.destroy();}
  const allKnown=nodes.length>0&&nodes.every(n=>stored[n.data.id]);
  // Cytoscape does not resolve CSS custom properties in its canvas styles.
  // Resolve the shared PAPIRO tokens to concrete colors before building the graph.
  const token=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const graphColors={
    text:token('--text')||'#1C1B19',
    muted:token('--text-muted')||'#6B6962',
    surface:token('--surface')||'#FFFFFF',
    bg:token('--bg')||'#FAFAF8',
    border:token('--border')||'#E7E5E0',
    accent:token('--accent')||'#B45309',
    accentSoft:token('--accent-soft')||'rgba(180,83,9,0.08)',
    accentPale:'#F8EBDD',
    accentBorder:'#D6A477',
    accentHover:token('--accent-hover')||'#92400E',
    success:token('--success')||'#15803D',
    successPale:'#E7F2E9',
    successBorder:'#8DB99A',
    warning:'#A16207'
  };
  cy=cytoscape({container:document.getElementById('cy'),elements:{nodes,edges},userZoomingEnabled:true,style:[
    {selector:'node',style:{'label':'data(label)','font-size':11,'font-family':'Inter, system-ui, sans-serif','color':graphColors.text,'text-wrap':'wrap','text-max-width':160,'text-background-color':graphColors.bg,'text-background-opacity':0.94,'text-background-padding':3,'background-color':graphColors.surface,'width':36,'height':36,'border-width':1.5,'border-color':graphColors.muted,'text-valign':'bottom','text-halign':'center','text-margin-y':8}},
    {selector:'node[node_type="finding"]',style:{'shape':'roundrectangle','background-color':graphColors.surface,'border-color':graphColors.muted,'color':graphColors.text,'width':58,'height':42,'font-size':10}},
    {selector:'node[node_type="indicator"]',style:{'shape':'ellipse','background-color':graphColors.accentPale,'border-color':graphColors.accentBorder,'width':30,'height':30,'color':graphColors.text,'font-size':10}},
    {selector:'node[node_type="entity"]',style:{'shape':'hexagon','background-color':graphColors.successPale,'border-color':graphColors.successBorder,'color':graphColors.text,'width':62,'height':62,'font-size':11,'font-weight':600}},
    {selector:'node[assessment="pertenece"]',style:{'border-color':graphColors.success,'border-width':3}},
    {selector:'node[assessment="no_pertenece"]',style:{'opacity':0.6,'border-style':'dashed'}},
    {selector:'node[relevance="no_relevante"]',style:{'opacity':0.5}},
    {selector:'edge',style:{'width':1.5,'line-color':graphColors.border,'target-arrow-color':graphColors.muted,'target-arrow-shape':'triangle','curve-style':'bezier','label':'','font-size':9,'font-family':'Inter, system-ui, sans-serif','color':graphColors.text,'text-background-color':graphColors.bg,'text-background-opacity':0.94,'text-background-padding':2}},
    {selector:'edge[edge_type="correlation"]',style:{'line-style':'dashed','line-color':graphColors.accentBorder,'target-arrow-color':graphColors.accentBorder,'label':'data(edge_type)','font-size':9}},
    {selector:'edge[edge_type="relationship"]',style:{'width':2,'line-color':graphColors.successBorder,'target-arrow-color':graphColors.successBorder,'label':'data(relationship_type)','font-size':9}},
    {selector:'.investigator-selected',style:{'border-width':3,'border-color':graphColors.accent,'background-color':graphColors.accentPale}},
    {selector:':selected',style:{'border-width':3,'border-color':graphColors.accent,'line-color':graphColors.accent,'target-arrow-color':graphColors.accent}}
  ],layout:allKnown&&preserve?{name:'preset',positions:n=>stored[n.id()],fit:false}:{name:'cose',animate:false,padding:80,nodeRepulsion:12000,idealEdgeLength:150}});
  // Let the browser handle ordinary wheel scrolling; Ctrl+wheel remains available for graph zoom.
  document.getElementById('cy').addEventListener('wheel',event=>{if(!event.ctrlKey)event.stopImmediatePropagation();},{capture:true});
  cy.on('dragfree','node',savePositions);
  cy.on('tap','node',e=>{selectedElement=e.target.data();const d=selectedElement;if(d.node_type==='finding')showFinding(d.id.replace('finding:',''));else if(d.node_type==='entity'){const id=d.id.replace('entity:','');showEntity(id);}else setDetails(`<div class="detail-title">Indicator</div><div class="detail-sub">${esc(d.indicator_type||'')}</div>${kv('Value',d.label)}${kv('Normalized',d.normalized_value)}${kv('Source',d.source||'')}`);});
  cy.on('tap','edge',e=>{const d=e.target.data();if(d.edge_type==='correlation')showCorrelation(d.correlation_id);else if(d.edge_type==='relationship')showRelationship(d.relationship_id);else setDetails(`<div class="detail-title">Evidence ↔ indicator</div>${kv('Evidence basis',d.basis||'')}`);});
  if(!allKnown&&preserve){const knownIds=Object.keys(stored);cy.one('layoutstop',()=>{knownIds.forEach(id=>{const n=cy.getElementById(id);if(n.length)n.position(stored[id]);});savePositions();});}
  else if(!allKnown)cy.one('layoutstop',savePositions);
  applyGraphFilters();syncGraphSelection();
}
function applyGraphFilters(){
  if(!cy)return;const type=document.getElementById('nodeTypeFilter').value,source=document.getElementById('sourceFilter').value,q=document.getElementById('findingSearch').value.trim().toLowerCase();
  const showIndicators=document.getElementById('showIndicators').checked,showCorrelations=document.getElementById('showCorrelations').checked,showMemberships=document.getElementById('showMemberships').checked;
  cy.nodes().forEach(n=>{const d=n.data(),hidden=hiddenNodeIds.has(n.id()),okType=type==='all'||d.node_type===type,okSource=source==='all'||!['finding','indicator'].includes(d.node_type)||d.source===source,hay=`${d.label||''} ${d.normalized_value||''}`.toLowerCase(),okQ=!q||hay.includes(q),okIndicator=showIndicators||d.node_type!=='indicator';n.style('display',!hidden&&okType&&okSource&&okQ&&okIndicator?'element':'none');});
  cy.edges().forEach(e=>{const d=e.data(),visible=e.source().style('display')!=='none'&&e.target().style('display')!=='none',okCorr=showCorrelations||d.edge_type!=='correlation',okMem=showMemberships||d.edge_type!=='entity_membership';e.style('display',visible&&okCorr&&okMem?'element':'none');});
}
async function runManualSearch(){const input=document.getElementById('manualSearch'),status=document.getElementById('searchStatus'),btn=document.getElementById('manualSearchBtn'),query=input.value.trim();if(query.length<2){status.textContent='Enter at least 2 characters.';return;}btn.disabled=true;status.textContent='Searching configured sources…';try{const r=await api(`/jobs/${encodeURIComponent(jobId)}/search/name`,{method:'POST',body:JSON.stringify({query})});status.textContent=`Search submitted. Updating results…`;let tries=0;const poll=setInterval(async()=>{tries++;try{await loadAll(true);if(findings.some(f=>f.input_value===query)){clearInterval(poll);status.textContent='Search complete. Results are now part of the investigation.';}else if(tries>=20){clearInterval(poll);status.textContent='The search is still processing; you can refresh later.';}}catch{}},1500);void r;}catch(e){status.textContent=`Could not run the search: ${e.message}`;}finally{setTimeout(()=>btn.disabled=false,1000);}}
async function loadAll(preserve=true){
  try{const [job,g,f,c,e,r]=await Promise.all([api(`/jobs/${encodeURIComponent(jobId)}`),api(`/jobs/${encodeURIComponent(jobId)}/graph`),api(`/jobs/${encodeURIComponent(jobId)}/findings`),api(`/jobs/${encodeURIComponent(jobId)}/correlations`),api(`/jobs/${encodeURIComponent(jobId)}/entities`),api(`/jobs/${encodeURIComponent(jobId)}/relationships`)]);graphData=g;findings=f;correlations=c;entities=e;relationships=r;if(job.is_shared){document.getElementById('shareInvestigationBtn').hidden=true;document.getElementById('mergeInvestigationBtn').hidden=true;}document.getElementById('jobLabel').textContent=`Investigation: ${job.investigation_title||job.input_value} · Status: ${job.status==='draft'?'Draft':job.status} · ID: ${job.id}`;const notesSection=document.getElementById('investigationNotesSection');notesSection.hidden=!job.notes;document.getElementById('investigationNotesText').textContent=job.notes||'';document.getElementById('nFindings').textContent=g.summary?.findings??job.finding_count??0;document.getElementById('nIndicators').textContent=g.summary?.indicators??0;document.getElementById('nCorrelations').textContent=g.summary?.correlations??job.correlation_count??0;document.getElementById('nEntities').textContent=g.summary?.entities??entities.length;const sf=document.getElementById('sourceFilter'),old=sf.value;sf.innerHTML='<option value="all">All sources</option>'+[...new Set(findings.map(f=>f.source))].sort().map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');sf.value=[...sf.options].some(o=>o.value===old)?old:'all';renderFindings();renderEntities();buildGraph(preserve);}catch(e){if(/Authentication required|HTTP 401|Invalid or expired token/i.test(e.message)){localStorage.removeItem(TOKEN_KEY);location.replace('/ui');return;}setDetails(`<div class="error"><b>Could not load the investigation.</b><p>${esc(e.message)}</p><p>Check that the API is running and the investigation exists.</p></div>`);}}
document.getElementById('sourceFilter').onchange=()=>{renderFindings();applyGraphFilters();};
document.getElementById('findingSearch').oninput=()=>{renderFindings();applyGraphFilters();};
document.getElementById('nodeTypeFilter').onchange=applyGraphFilters;
document.getElementById('showIndicators').onchange=applyGraphFilters;
document.getElementById('showCorrelations').onchange=applyGraphFilters;
document.getElementById('showMemberships').onchange=applyGraphFilters;
function zoomGraphBy(factor){if(!cy)return;const level=Math.max(cy.minZoom(),Math.min(cy.maxZoom(),cy.zoom()*factor));cy.zoom({level,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});}
document.getElementById('zoomOutBtn').onclick=()=>zoomGraphBy(1/1.2);
document.getElementById('zoomInBtn').onclick=()=>zoomGraphBy(1.2);
document.getElementById('fitBtn').onclick=()=>cy?.fit(cy.elements(':visible'),50);
document.getElementById('resetGraphBtn').onclick=()=>{hiddenNodeIds.clear();persistHidden();document.getElementById('nodeTypeFilter').value='all';document.getElementById('sourceFilter').value='all';document.getElementById('findingSearch').value='';document.getElementById('showIndicators').checked=true;document.getElementById('showCorrelations').checked=true;document.getElementById('showMemberships').checked=true;renderFindings();applyGraphFilters();cy?.fit(cy.elements(':visible'),50);};
document.getElementById('hideSelectedBtn').onclick=hideSelected;document.getElementById('showHiddenBtn').onclick=showAllHidden;document.getElementById('selectVisible').onclick=selectVisible;document.getElementById('clearSelection').onclick=clearSelection;document.getElementById('createEntityBtn').onclick=openEntityModal;document.getElementById('saveEntityBtn').onclick=saveEntity;document.getElementById('saveEntityEditBtn').onclick=saveEntityEdit;document.getElementById('saveRelationshipBtn').onclick=saveRelationship;document.getElementById('saveRelationshipEditBtn').onclick=saveRelationshipEdit;document.getElementById('manualSearchBtn').onclick=runManualSearch;document.getElementById('manualSearch').addEventListener('keydown',e=>{if(e.key==='Enter')runManualSearch();});document.getElementById('reloadBtn').onclick=()=>loadAll(true);
document.getElementById('sharedCommentsBtn').onclick=async()=>{try{const job=await api('/jobs/'+encodeURIComponent(jobId));let share;if(job.is_owner){const shares=await api('/jobs/'+encodeURIComponent(jobId)+'/shares');if(!shares.length){alert('This investigation has no shared copies yet.');return;}const choice=prompt('Which investigator’s copy would you like to comment on?\\n'+shares.map((s,i)=>(i+1)+'. '+s.email).join('\\n'));const index=Number(choice)-1;if(!Number.isInteger(index)||index<0||index>=shares.length)return;share=shares[index];}else{const shares=await api('/shared-investigations');share=shares.find(s=>s.job_id===jobId);if(!share){alert('No comment thread was found for this copy.');return;}}const show=async()=>{const comments=await api('/shares/'+encodeURIComponent(share.share_id)+'/comments');alert(comments.map(c=>c.author_email+': '+c.body).join('\\n\\n')||'There are no comments yet.');};await show();if(!job.is_owner&&share.permission==='read')return;const body=prompt('Write a comment for this proposal:');if(body&&body.trim()){await api('/shares/'+encodeURIComponent(share.share_id)+'/comments',{method:'POST',body:JSON.stringify({body})});await show();}}catch(error){alert(error.message);}};
document.getElementById('shareInvestigationBtn').onclick=()=>{document.getElementById('shareError').textContent='';document.getElementById('shareResult').textContent='';openModal('shareInvestigationModal');};
document.getElementById('shareInvestigationForm').addEventListener('submit',async event=>{event.preventDefault();const button=document.getElementById('shareSubmitBtn');button.disabled=true;document.getElementById('shareError').textContent='';document.getElementById('shareResult').textContent='';try{const result=await api('/jobs/'+encodeURIComponent(jobId)+'/shares',{method:'POST',body:JSON.stringify({email:document.getElementById('shareEmail').value.trim(),permission:document.getElementById('sharePermission').value})});document.getElementById('shareResult').innerHTML='Copy created. Share this link with the investigator: <a href="/ui/job/'+encodeURIComponent(result.shared_job_id)+'">Open shared copy</a>';document.getElementById('shareEmail').value='';}catch(error){document.getElementById('shareError').textContent=error.message;}finally{button.disabled=false;}});
document.getElementById('mergeInvestigationBtn').onclick=async()=>{openModal('mergeInvestigationModal');const list=document.getElementById('sharedCopiesList');list.textContent='Loading copies…';document.getElementById('mergeError').textContent='';try{const shares=await api('/jobs/'+encodeURIComponent(jobId)+'/shares');if(!shares.length){list.textContent='There are no shared copies yet.';return;}list.innerHTML=shares.map(s=>'<div class="panel-card"><b>'+esc(s.email)+'</b><p>Permission: '+esc(s.permission)+' · Shared: '+esc(new Date(s.created_at).toLocaleString("en-US"))+'</p><p>Review status: '+(s.reviewed?'Reviewed; no subsequent changes':'Pending review')+'</p><a href="/ui/job/'+encodeURIComponent(s.shared_job_id)+'">Open copy</a> <button type="button" data-review-share="'+esc(s.share_id)+'">Review changes</button> <button type="button" data-merge-share="'+esc(s.share_id)+'" '+(s.reviewed?'':'disabled')+'>Pull / Merge</button> <button type="button" data-comment-share="'+esc(s.share_id)+'">Comments</button><div data-review-result="'+esc(s.share_id)+'"></div></div>').join('');list.querySelectorAll('[data-review-share]').forEach(button=>button.onclick=async()=>{const shareId=button.dataset.reviewShare;const target=list.querySelector('[data-review-result="'+shareId+'"]');target.textContent='Calculating differences…';try{const review=await api('/jobs/'+encodeURIComponent(jobId)+'/shares/'+encodeURIComponent(shareId)+'/review');if(!review.changes.length){target.innerHTML='<p>No changes were detected against the shared baseline.</p>';}else{target.innerHTML='<h4>Changes detected</h4>'+review.changes.map(c=>'<section><b>'+esc(c.table)+'</b><p>Added: '+c.added+' · Removed: '+c.deleted+' · Modified: '+c.modified+'</p><ul>'+c.details.map(d=>'<li><b>'+esc(d.operation)+' · '+esc(d.id)+'</b>'+(d.values?'<dl>'+((Array.isArray(d.values)?d.values:Object.entries(d.values).map(([field,value])=>({field,before:d.operation==='deleted'?value:undefined,after:d.operation==='deleted'?undefined:value}))).map(v=>'<dt>'+esc(v.field||'value')+'</dt><dd><div><small>Before:</small> '+esc(v.before===undefined?'—':String(v.before))+'</div><div><small>After:</small> '+esc(v.after===undefined?'—':String(v.after))+'</div></dd>').join(''))+'</dl>':'')+'</li>').join('')+'</ul></section>').join('');}const mark=document.createElement('button');mark.type='button';mark.textContent='Mark this version as reviewed';mark.onclick=async()=>{mark.disabled=true;try{await api('/jobs/'+encodeURIComponent(jobId)+'/shares/'+encodeURIComponent(shareId)+'/review',{method:'POST',body:JSON.stringify({snapshot_token:review.snapshot_token})});target.insertAdjacentHTML('beforeend','<p>Version reviewed. If the collaborator makes further changes, it must be reviewed again.</p>');const mergeButton=list.querySelector('[data-merge-share="'+shareId+'"]');if(mergeButton)mergeButton.disabled=false;const status=button.parentElement.querySelector('p:nth-of-type(2)');if(status)status.textContent='Review status: Reviewed; no subsequent changes';}catch(error){target.insertAdjacentHTML('beforeend','<p class="error">'+esc(error.message)+'</p>');}finally{mark.disabled=false;}};target.appendChild(mark);}catch(error){target.textContent='Could not review the proposal: '+error.message;}});list.querySelectorAll('[data-merge-share]').forEach(button=>button.onclick=async()=>{if(button.disabled)return;if(!confirm('Merge the reviewed version into the original investigation?'))return;button.disabled=true;try{await api('/jobs/'+encodeURIComponent(jobId)+'/shares/'+encodeURIComponent(button.dataset.mergeShare)+'/merge',{method:'POST'});document.getElementById('mergeError').textContent='Merge complete. The original investigation has been updated.';await loadAll(true);button.textContent='Merged';}catch(error){document.getElementById('mergeError').textContent=error.message;const conflicts=error.details?.conflicts;const target=list.querySelector('[data-review-result="'+button.dataset.mergeShare+'"]');if(conflicts?.length&&target){target.innerHTML='<h4>Conflicts that need a decision</h4><p>Keep a version by editing the original or asking the collaborator to update their copy; then review the proposal again.</p><ul>'+conflicts.map(c=>'<li><b>'+esc(c.table)+' · '+esc(c.id)+' · '+esc(c.field)+'</b><p>'+esc(c.reason||'The same field changed in both versions')+'</p><dl><dt>Base version</dt><dd>'+esc(c.base===undefined?'—':String(c.base))+'</dd><dt>Original</dt><dd>'+esc(c.original===undefined?'—':String(c.original))+'</dd><dt>Proposed</dt><dd>'+esc(c.proposed===undefined?'—':String(c.proposed))+'</dd></dl></li>').join('')+'</ul>';}}finally{button.disabled=false;}});list.querySelectorAll('[data-comment-share]').forEach(button=>button.onclick=async()=>{try{const shareId=button.dataset.commentShare;const comments=await api('/shares/'+encodeURIComponent(shareId)+'/comments');alert(comments.map(c=>c.author_email+': '+c.body).join('\\n\\n')||'There are no comments yet.');const body=prompt('Write a comment for this proposal:');if(body&&body.trim())await api('/shares/'+encodeURIComponent(shareId)+'/comments',{method:'POST',body:JSON.stringify({body})});}catch(error){document.getElementById('mergeError').textContent=error.message;}});}catch(error){list.textContent='Could not load copies: '+error.message;}};

 document.addEventListener('DOMContentLoaded',()=>{
  const sessionModal=document.getElementById('sessionModal');
  const baselineKey=`kami:session-baseline:${jobId}`;
  const hiddenKey=`kami:hidden:${jobId}`;
  let checkpointReady=false;
  let checkpointPromise=null;
  let exitInProgress=false;
  // Fail closed until the server confirms that this investigation is editable.
  let readOnlySession=true;
  document.addEventListener('click',event=>{
    if(!readOnlySession)return;
    const button=event.target.closest('button');
    if(!button)return;
    const handler=button.getAttribute('onclick')||'';
    const mutatingIds=new Set(['manualSearchBtn','createEntityBtn','saveEntityBtn','saveEntityEditBtn',
      'saveRelationshipBtn','saveRelationshipEditBtn','shareInvestigationBtn','mergeInvestigationBtn']);
    if(mutatingIds.has(button.id)||/assessFinding|assessRelationship|assessCorrelation|saveEntity|saveRelationship|openEntityEdit|openRelationshipEdit|attachSelectedFindingsToEntity/.test(handler)){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);
  document.addEventListener('keydown',event=>{
    if(readOnlySession&&event.target?.id==='manualSearch'&&event.key==='Enter'){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);
  document.addEventListener('submit',event=>{
    if(readOnlySession&&event.target?.id==='shareInvestigationForm'){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);
  const openSessionModal=()=>{sessionModal.style.display='flex';};
  const activateReadOnlyMode=()=>{
    readOnlySession=true;
    const status=document.getElementById('saveStatus');
    if(status)status.textContent='Read-only access';
    ['manualSearch','manualSearchBtn','createEntityBtn','saveEntityBtn','saveEntityEditBtn',
     'saveRelationshipBtn','saveRelationshipEditBtn','shareInvestigationBtn','mergeInvestigationBtn']
      .forEach(id=>{const control=document.getElementById(id);if(control)control.disabled=true;});
  };
  window.detectReadOnlySession=async()=>{
    const job=await api(`/jobs/${encodeURIComponent(jobId)}`);
    if(job?.can_edit===false){activateReadOnlyMode();return true;}
    if(!job?.is_shared){readOnlySession=false;return false;}
    if(!job.is_owner){activateReadOnlyMode();return true;}
    const shares=await api('/shared-investigations');
    const share=shares.find(item=>item.job_id===jobId);
    if(share && share.permission!=='edit'){activateReadOnlyMode();return true;}
    readOnlySession=false;
    return false;
  };
  const setExitProgress=message=>{const status=document.getElementById('exitProgress');if(status){status.textContent=message||'';status.hidden=!message;}};
  const closeSessionModal=()=>{if(!exitInProgress){setExitProgress('');sessionModal.style.display='none';}};
  const saveView=()=>{if(cy)savePositions();persistHidden();};
  const rememberLocalBaseline=(checkpointId)=>{
    let existing=null;
    try{existing=JSON.parse(localStorage.getItem(baselineKey)||'null');}catch{}
    if(existing?.checkpointId===checkpointId)return;
    localStorage.setItem(baselineKey,JSON.stringify({
      checkpointId,
      positions:localStorage.getItem(positionKey),
      hidden:localStorage.getItem(hiddenKey)
    }));
  };
  const restoreLocalBaseline=()=>{
    let baseline=null;
    try{baseline=JSON.parse(localStorage.getItem(baselineKey)||'null');}catch{}
    if(baseline){
      if(baseline.positions===null)localStorage.removeItem(positionKey);else localStorage.setItem(positionKey,baseline.positions);
      if(baseline.hidden===null)localStorage.removeItem(hiddenKey);else localStorage.setItem(hiddenKey,baseline.hidden);
      try{hiddenNodeIds=new Set(JSON.parse(localStorage.getItem(hiddenKey)||'[]'));}catch{hiddenNodeIds=new Set();}
    }
    localStorage.removeItem(baselineKey);
  };
  const closeCheckpoint=async()=>{
    await api(`/jobs/${encodeURIComponent(jobId)}/checkpoint/commit`,{method:'POST'});
    localStorage.removeItem(baselineKey);
  };
  const leaveToWorkspace=async()=>{
    if(exitInProgress)return;exitInProgress=true;
    if(readOnlySession||!checkpointReady){restoreLocalBaseline();location.href='/ui/workspace';return;}
    setExitProgress('Confirming saved changes…');
    try{await window.beginInvestigationEditingSession();saveView();await closeCheckpoint();location.href='/ui/workspace';}
    catch(e){exitInProgress=false;setExitProgress('');alert(`Could not confirm changes. The session is still open. ${e.message}`);}
  };
  const leaveWithoutSaving=async()=>{
    if(exitInProgress)return;exitInProgress=true;
    if(readOnlySession||!checkpointReady){restoreLocalBaseline();location.href='/ui/workspace';return;}
    setExitProgress('Restoring the initial state… if a search is running, wait for it to finish.');
    try{
      await window.beginInvestigationEditingSession();
      await api(`/jobs/${encodeURIComponent(jobId)}/checkpoint/restore`,{method:'POST'});
      restoreLocalBaseline();
      location.href='/ui/workspace';
    }catch(e){exitInProgress=false;setExitProgress('');alert(`Could not discard the session. Do not leave the investigation until this error is resolved. ${e.message}`);}
  };
  const logoutAndClearView=async()=>{
    if(exitInProgress)return;exitInProgress=true;
    if(readOnlySession||!checkpointReady){restoreLocalBaseline();localStorage.removeItem(TOKEN_KEY);location.replace('/ui');return;}
    setExitProgress('Restoring the initial state before signing out…');
    try{
      await window.beginInvestigationEditingSession();
      await api(`/jobs/${encodeURIComponent(jobId)}/checkpoint/restore`,{method:'POST'});
      restoreLocalBaseline();
      localStorage.removeItem(TOKEN_KEY);location.replace('/ui');
    }catch(e){exitInProgress=false;setExitProgress('');alert(`Could not discard the session or sign out. ${e.message}`);}
  };
  const saveAndLogout=async()=>{
    if(exitInProgress)return;exitInProgress=true;
    if(readOnlySession||!checkpointReady){restoreLocalBaseline();localStorage.removeItem(TOKEN_KEY);location.replace('/ui');return;}
    setExitProgress('Confirming changes before signing out…');
    try{await window.beginInvestigationEditingSession();saveView();await closeCheckpoint();localStorage.removeItem(TOKEN_KEY);location.replace('/ui');}
    catch(e){exitInProgress=false;setExitProgress('');alert(`Could not save changes. The session is still open. ${e.message}`);}
  };
  window.beginInvestigationEditingSession=()=>{
    if(checkpointReady)return Promise.resolve();
    if(checkpointPromise)return checkpointPromise;
    checkpointPromise=(async()=>{
      const checkpoint=await api(`/jobs/${encodeURIComponent(jobId)}/checkpoint`,{method:'POST'});
      rememberLocalBaseline(checkpoint.checkpoint_id);
      checkpointReady=true;
      return checkpoint;
    })().catch(error=>{checkpointPromise=null;throw error;});
    return checkpointPromise;
  };
  document.getElementById('authBtn').onclick=openSessionModal;
  document.getElementById('cancelSessionExit').onclick=closeSessionModal;
  document.getElementById('leaveWithoutSaving').onclick=leaveWithoutSaving;
  document.getElementById('saveAndLeave').onclick=leaveToWorkspace;
  document.getElementById('saveAndLogout').onclick=saveAndLogout;
  document.getElementById('logoutWithoutViewSave').onclick=logoutAndClearView;
    document.getElementById('workspaceLink').onclick=e=>{e.preventDefault();openSessionModal();};
  sessionModal.addEventListener('click',e=>{if(e.target===sessionModal)closeSessionModal();});
 });
 document.addEventListener('DOMContentLoaded',()=>{
   // These authentication dialogs are declared after this script in the document.
   // Bind them only after parsing completes; a null-element exception here used to
   // abort initialization of the graph's exit and logout controls.
   const closeLoginBtn=document.getElementById('closeLoginBtn');
   const showLoginTab=document.getElementById('showLoginTab');
   const showRegisterTab=document.getElementById('showRegisterTab');
   const loginForm=document.getElementById('loginForm');
   const registerForm=document.getElementById('registerForm');
   if(closeLoginBtn) closeLoginBtn.onclick=()=>closeModal('loginModal');
   if(showLoginTab) showLoginTab.onclick=()=>showAuthTab('login');
   if(showRegisterTab) showRegisterTab.onclick=()=>showAuthTab('register');
   if(loginForm) loginForm.addEventListener('submit',submitLogin);
   if(registerForm) registerForm.addEventListener('submit',submitRegister);
   updateAuthButton();
   (async()=>{
     const token=localStorage.getItem(TOKEN_KEY);
     if(!token){location.replace('/ui');return;}
     try{
       await api('/auth/me');
       const isReadOnly=await window.detectReadOnlySession();
       if(!isReadOnly)await beginInvestigationEditingSession();
       await loadAll(true);
     }catch(error){
       if(/Authentication required|HTTP 401|Invalid or expired token/i.test(error.message)){
         localStorage.removeItem(TOKEN_KEY);
         location.replace('/ui');
       }else{
         setDetails(`<div class="error"><b>Could not start the editing session.</b><p>${esc(error.message)}</p><p>The investigation has not been modified. You can return to the workspace and try again.</p></div>`);
       }
     }
   })();
 });
