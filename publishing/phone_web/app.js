'use strict';
const byId = id => document.getElementById(id);
const storageKey = 'slade.phone.prototype.drafts.v1';
let config, currentId = null, revision = null, sourceGroups = [], epoch = 0, pollTimer, creating = false, saving = false;
function announce(message) { byId('status').textContent = message; }
function show(screen) {
  epoch++; clearTimeout(pollTimer);
  for (const name of ['home','editor','review','projects','result']) byId(name).hidden = name !== screen;
  byId(screen+'-title').focus(); window.scrollTo(0,0);
  if (screen !== 'result') history.replaceState(null,'',location.pathname);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',
    headers:{'Content-Type':'application/json','X-Studio-Request':'plan'},body:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'The Studio could not finish this request.');
  return value;
}
function options(id,values) { for (const [value,label] of values) byId(id).add(new Option(label,value)); }
function planFromForm() {
  const value = {title:byId('title').value.trim(),theme:byId('theme').value,
    reader_profile:byId('reader').value,activity_count:Number(byId('count').value),
    formats:[...document.querySelectorAll('[name="format"]:checked')].map(el=>el.value),theme_balance:byId('balance').value};
  if (sourceGroups.length) value.source_groups = [...sourceGroups];
  validate(value); return value;
}
function validate(plan, currentTheme = true) {
  if (!plan || typeof plan.title !== 'string' || !plan.title.trim() || plan.title.length > 100 ||
      typeof plan.theme !== 'string' || plan.theme.length > 100 ||
      (currentTheme && !config.themes.includes(plan.theme) && !plan.source_groups?.length) ||
      !Object.hasOwn(config.readers,plan.reader_profile) || !config.balances.includes(plan.theme_balance) ||
      !Number.isInteger(plan.activity_count) || plan.activity_count < 1 || plan.activity_count > 24 ||
      !Array.isArray(plan.formats) || !plan.formats.length ||
      new Set(plan.formats).size !== plan.formats.length || plan.formats.some(f=>!config.formats.includes(f)))
    throw new Error('Choose a name, theme, reader and at least one activity.');
}
function fillForm(plan) {
  sourceGroups = plan.source_groups || [];
  if (!config.themes.includes(plan.theme) && sourceGroups.length && ![...byId('theme').options].some(o=>o.value===plan.theme))
    byId('theme').add(new Option(plan.theme,plan.theme));
  for (const [id,key] of Object.entries({title:'title',theme:'theme',reader:'reader_profile',count:'activity_count',balance:'theme_balance'})) byId(id).value=plan[key];
  for (const input of document.querySelectorAll('[name="format"]')) input.checked=plan.formats.includes(input.value);
  byId('sources').textContent=sourceGroups.length ? 'Proposed groups: '+sourceGroups.join(', ') : '';
}
async function review() {
  const ticket=++epoch, button=byId('review-button');
  try {
    const plan=planFromForm(); button.disabled=true; button.textContent='Checking the word bank…';
    announce('Choosing checked words for your theme and reader.');
    const result=await api('/api/plan',plan);
    if (ticket!==epoch) return;
    if (JSON.stringify(plan)!==JSON.stringify(planFromForm())) throw new Error('Your choices changed. Check the updated plan again.');
    const fields={'Pack':plan.title,'Theme':plan.theme,'Reader':config.readers[plan.reader_profile],
      'Activities':plan.formats.join(', '),'Activity pages':String(plan.activity_count),'Theme mix':plan.theme_balance,
      'Checked vocabulary':result.word_count ? `${result.word_count} different words` : 'Not needed for Sudoku-only activities',
      'Groups used':Object.keys(result.group_counts).join(', ') || 'Number puzzles'};
    byId('plan-summary').replaceChildren();
    for (const [label,value] of Object.entries(fields)) {
      const dt=document.createElement('dt'),dd=document.createElement('dd'); dt.textContent=label;dd.textContent=value;byId('plan-summary').append(dt,dd);
    }
    byId('plan-notes').replaceChildren();
    for (const note of result.notes) {const p=document.createElement('p');p.textContent=note;byId('plan-notes').append(p);}
    announce('Vocabulary checked. Review your choices, then create your pack.');show('review');
  } catch(error) {if(ticket===epoch) announce(error.message);}
  finally {button.disabled=false;button.textContent='Check and review my plan →';}
}
async function saveProject() {
  const ticket=epoch, request=planFromForm(), original=currentId;
  const record=await api('/api/projects',{request,id:currentId,revision});
  if(ticket!==epoch || original!==currentId || JSON.stringify(request)!==JSON.stringify(planFromForm())) throw new Error('The project was saved on the HP, but your screen changed. Open it from My projects.');
  currentId=record.id;revision=record.revision;return record;
}
async function save() {
  byId('save').disabled=true;
  try {await saveProject();announce('Project saved on the HP. Find it in My projects.');}
  catch(error) {announce(error.message);}
  finally {saving=false;byId('save').disabled=false;byId('generate').disabled=false;}
}
async function create() {
  if(creating || saving) return; creating=true;byId('generate').disabled=true;byId('save').disabled=true;
  try {
    const record=await saveProject(), ticket=epoch;
    const result=await api('/api/create',{id:record.id,revision:record.revision});
    if(ticket===epoch) await openJob(result.job);
  } catch(error) {announce(error.message);}
  finally {creating=false;byId('generate').disabled=false;byId('save').disabled=false;}
}
function openProject(record) {
  currentId=record.id;revision=record.revision;fillForm(record.request);show('editor');
  announce('Reopened the saved project. Check word availability before creating.');
}
async function projects() {
  show('projects');const ticket=epoch;byId('drafts').textContent='Loading saved projects…';
  try {
    const value=await api('/api/projects');if(ticket!==epoch) return;
    byId('drafts').replaceChildren();
    if(!value.projects.length) byId('drafts').textContent='No saved projects yet. Create an activity pack to begin.';
    for(const record of value.projects) {
      const card=document.createElement('article');card.className='draft';
      const h=document.createElement('h2'),p=document.createElement('p'),edit=document.createElement('button');
      h.textContent=record.request.title;p.textContent=`${record.request.theme} · ${record.request.activity_count} activity pages · revision ${record.revision}`;
      edit.textContent='Edit project';edit.addEventListener('click',()=>openProject(record));card.append(h,p,edit);
      for(const job of record.jobs.slice(0,5)) {
        const button=document.createElement('button');button.textContent=`${job.stage} · revision ${job.revision}`;
        button.addEventListener('click',()=>openJob(job.id));card.append(button);
      }
      byId('drafts').append(card);
    }
    announce('Projects and completed packs are saved on this HP.');
  } catch(error) {if(ticket===epoch) {announce(error.message);byId('drafts').textContent='Could not load projects. Try My projects again.';}}
  renderLegacyDrafts();
}
function renderLegacyDrafts() {
  byId('legacy-drafts').replaceChildren();
  try {
    const rows=JSON.parse(localStorage.getItem(storageKey)||'[]');
    if(!Array.isArray(rows)||rows.length>50) throw new Error('Earlier browser drafts could not be read.');
    for(const row of rows) {
      validate(row.plan,false);const button=document.createElement('button');
      button.className='secondary';button.textContent='Import earlier browser draft: '+row.plan.title;
      button.addEventListener('click',()=>{currentId=null;revision=null;fillForm(row.plan);show('editor');announce('Review these earlier choices, select a current library theme if needed, then save on the HP. The browser copy is preserved.');});
      byId('legacy-drafts').append(button);
    }
  } catch(error) {byId('legacy-drafts').textContent='Earlier browser drafts are unavailable. Their stored data has not been changed.';}
}
async function openJob(id) {
  show('result');history.replaceState(null,'','#job-'+id);const ticket=epoch;
  byId('job-stage').textContent='Loading pack…';byId('downloads').hidden=true;byId('preview-area').hidden=true;byId('job-error').textContent='';
  async function refresh() {
    try {
      const job=await api('/api/jobs/'+id);if(ticket!==epoch) return;
      byId('job-stage').textContent=job.stage;byId('job-error').textContent=job.error;
      if(job.status==='ready') {
        byId('downloads').hidden=false;byId('preview-area').hidden=false;
        for(const kind of ['activities','answers','zip']) byId('download-'+kind).href=`/api/files/${id}/${kind}`;
        byId('preview-kind').onchange=()=>loadPreview(id,Number(byId('preview-page').value));
        byId('preview-page').onchange=()=>loadPreview(id,Number(byId('preview-page').value));
        const count=job.activity_count;
        byId('result-title').textContent=job.title;
        // The immutable job may be an older revision; the server bounds every page.
        byId('preview-page').replaceChildren();options('preview-page',Array.from({length:count+1},(_,page)=>[String(page),page===0?'Introduction':`Activity ${page}`]));
        loadPreview(id,0);announce('Pack ready. Review the actual pages before printing or sharing.');
      } else if(['queued','running'].includes(job.status)) {
        pollTimer=setTimeout(refresh,1500);
      } else {announce('Your project is saved. Open My projects to edit or retry creating it.');}
    } catch(error) {
      if(ticket!==epoch) return;
      byId('job-error').textContent='Connection interrupted. The saved job remains on the HP. Reconnecting…';
      pollTimer=setTimeout(refresh,4000);
    }
  }
  await refresh();
}
function loadPreview(id,page) {
  byId('preview-image').src=`/api/preview/${id}/${byId('preview-kind').value}/${page}`;
  byId('preview-image').alt=`Actual ${byId('preview-kind').value} page ${page+1}`;
}
async function assist() {
  const button=byId('ask-ai'),ticket=epoch;button.disabled=true;button.textContent='Asking ChatGPT/Codex…';
  try {
    announce('One AI request is running. It will propose choices for you to review.');
    const result=await api('/api/assist',{text:byId('idea').value});if(ticket!==epoch) return;
    currentId=null;revision=null;fillForm(result.request);show('editor');
    announce('ChatGPT/Codex proposed these choices. Review activities, reader and theme groups before continuing.');
  } catch(error) {if(ticket===epoch) announce(error.message);}
  finally {button.disabled=false;button.textContent='Ask ChatGPT/Codex';}
}
async function start() {
  try {
    config=await api('/api/config');options('theme',config.themes.map(v=>[v,v]));
    byId('theme').querySelector('option[value="Homesteading"]').defaultSelected=true;
    options('reader',Object.entries(config.readers));options('balance',config.balances.map(v=>[v,v]));
    options('count',Array.from({length:24},(_,i)=>[String(i+1),String(i+1)]));byId('count').options[5].defaultSelected=true;
    for(const value of config.formats) {
      const label=document.createElement('label'),input=document.createElement('input');
      input.type='checkbox';input.name='format';input.value=value;input.defaultChecked=true;input.checked=true;
      label.append(input,document.createTextNode(value));byId('formats').append(label);
    }
    byId('create').addEventListener('click',()=>{currentId=null;revision=null;sourceGroups=[];byId('plan-form').reset();byId('sources').textContent='';announce('Choose your activities. We select checked words for you.');show('editor');});
    byId('theme').addEventListener('change',()=>{sourceGroups=[];byId('sources').textContent='';});
    byId('projects-button').addEventListener('click',projects);byId('result-projects').addEventListener('click',projects);
    byId('plan-form').addEventListener('submit',event=>{event.preventDefault();review();});
    byId('edit').addEventListener('click',()=>{announce('');show('editor');});
    byId('save').addEventListener('click',save);byId('generate').addEventListener('click',create);byId('ask-ai').addEventListener('click',assist);
    byId('preview-image').addEventListener('error',()=>{byId('preview-note').textContent='This page could not be loaded. Select another page or download the PDF.';});
    byId('preview-image').addEventListener('load',()=>{byId('preview-note').textContent='';});
    for(const el of document.querySelectorAll('[data-home],.brand')) el.addEventListener('click',event=>{event.preventDefault();announce('');show('home');});
    const job=location.hash.match(/^#job-([a-f0-9]{32})$/);if(job) await openJob(job[1]);else {announce('');show('home');}
  } catch(error) {announce('Could not connect to the Studio. Start its launcher on the HP, then reload.');}
}
start();

