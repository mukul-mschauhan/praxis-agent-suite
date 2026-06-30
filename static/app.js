const EXAMPLES = [
  "Our mid-market SaaS company is losing customers to low-cost regional competitors. We are considering a 20% price cut but are worried about margin impact and whether it could trigger predatory-pricing scrutiny in two of our markets.",
  "We need to cut $4M in annual operating cost and are evaluating a 15% workforce reduction across two manufacturing sites. Leadership wants this done quietly without triggering union escalation or reputational damage.",
  "We are a US-based fintech evaluating entry into the UAE market within 12 months. We don't yet know our competitive position there or what regulatory exposure we'd face."
];

document.querySelectorAll('.chip').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.getElementById('brief').value = EXAMPLES[btn.dataset.ex];
  });
});

document.getElementById('runBtn').addEventListener('click', runEngagement);
document.getElementById('skillsBtn').addEventListener('click', openSkillsModal);
document.getElementById('closeSkills').addEventListener('click', ()=> {
  document.getElementById('skillsModal').classList.add('hidden');
});

async function openSkillsModal(){
  const modal = document.getElementById('skillsModal');
  const content = document.getElementById('skillsContent');
  modal.classList.remove('hidden');
  content.innerHTML = '<p>Loading skill definitions...</p>';
  try{
    const res = await fetch('/api/skills');
    const data = await res.json();
    content.innerHTML = Object.entries(data).map(([name, text]) => `
      <details>
        <summary>${name}</summary>
        <pre>${escapeHtml(text)}</pre>
      </details>
    `).join('');
  }catch(e){
    content.innerHTML = '<p>Failed to load skills.</p>';
  }
}

function escapeHtml(str){
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function runEngagement(){
  const apiKey = document.getElementById('apiKey').value.trim();
  const brief = document.getElementById('brief').value.trim();
  const statusEl = document.getElementById('status');
  const runBtn = document.getElementById('runBtn');

  if(!apiKey){ statusEl.textContent = 'Please enter your Anthropic API key.'; return; }
  if(brief.length < 10){ statusEl.textContent = 'Please describe the client problem in more detail.'; return; }

  runBtn.disabled = true;
  statusEl.textContent = 'Routing brief to specialist agents... this can take 20-60 seconds.';
  document.getElementById('pipelineViz').innerHTML = '<div class="empty-state">Running engagement...</div>';
  document.getElementById('traceAccordion').innerHTML = '';
  document.getElementById('reportArea').innerHTML = '<div class="empty-state">Working...</div>';

  try{
    const res = await fetch('/api/run', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({api_key: apiKey, brief})
    });
    const data = await res.json();
    if(!res.ok){
      statusEl.textContent = 'Error: ' + (data.error || 'unknown error');
      runBtn.disabled = false;
      return;
    }
    statusEl.textContent = 'Engagement complete.';
    renderPipeline(data);
    renderTrace(data.trace);
    renderReport(data);
  }catch(e){
    statusEl.textContent = 'Request failed: ' + e.message;
  }
  runBtn.disabled = false;
}

function renderPipeline(data){
  const viz = document.getElementById('pipelineViz');
  const steps = [];
  steps.push({label:'Router', meta: data.router_decision?.reasoning || 'decided agent selection'});
  data.selected_skills.forEach(s => steps.push({label: prettyName(s), meta:'specialist agent'}));
  steps.push({label:'Strategy Synthesis', meta: data.revision_occurred ? 'ran twice (revised after QA)' : 'single pass'});
  steps.push({label:'Evaluation (QA)', meta: data.evaluation?.verdict || ''});

  // attach guardrail status per step by matching trace
  const statusByStep = {};
  (data.trace || []).forEach(t=>{
    if(t.guardrails){ statusByStep[t.step] = t.guardrails.status; }
  });

  let html = '';
  steps.forEach((s,i)=>{
    let key = null;
    if(i===0) key='agent:router';
    else if(i <= data.selected_skills.length) key = 'agent:' + data.selected_skills[i-1];
    else if(s.label==='Strategy Synthesis') key='agent:strategy_synthesis';
    else if(s.label.startsWith('Evaluation')) key='agent:evaluation';
    const status = statusByStep[key] || 'PASS';
    html += `<div class="node status-${status}"><div class="label">${s.label}</div><div class="meta">${escapeHtml(s.meta)}</div></div>`;
    if(i < steps.length-1) html += '<div class="arrow">→</div>';
  });
  viz.innerHTML = html;
}

function prettyName(s){
  return s.split('_').map(w=>w[0].toUpperCase()+w.slice(1)).join(' ');
}

function renderTrace(trace){
  const el = document.getElementById('traceAccordion');
  el.innerHTML = (trace || []).map((t,i)=>{
    const g = t.guardrails;
    const badge = g ? `<span class="badge">${g.status}</span>` : '';
    return `
      <div class="trace-item" data-idx="${i}">
        <div class="trace-head" onclick="this.parentElement.classList.toggle('open')">
          <span>${i+1}. ${t.step}</span>
          <span>${badge} <span class="badge">${t.latency_seconds ?? ''}s</span></span>
        </div>
        <div class="trace-body">
          <p><strong>Prompt sent:</strong></p>
          <pre>${escapeHtml(t.input_prompt || '')}</pre>
          <p><strong>Raw model output:</strong></p>
          <pre>${escapeHtml(t.output_raw || '')}</pre>
          ${g ? `<p><strong>Guardrail check:</strong></p><pre>${escapeHtml(JSON.stringify(g, null, 2))}</pre>` : ''}
          <p><strong>Tokens:</strong> in=${t.input_tokens ?? '-'} out=${t.output_tokens ?? '-'}</p>
        </div>
      </div>
    `;
  }).join('');
}

function renderReport(data){
  const el = document.getElementById('reportArea');
  const report = data.final_report || {};
  const evalr = data.evaluation || {};

  let html = '';

  if(data.hard_stop_triggered || report.decline_or_redirect){
    html += `<div class="decline-banner"><strong>Engagement declined / redirected.</strong><br>${escapeHtml(data.hard_stop_reason || report.decline_reason || 'A risk agent flagged a hard stop.')}</div>`;
  }

  html += `<div class="section-title">Executive Summary</div>`;
  html += `<p class="exec">${escapeHtml(report.executive_summary || '—')}</p>`;

  html += `<div class="section-title">Recommended Actions</div>`;
  (report.recommended_actions || []).forEach(a=>{
    html += `<div class="action-item">${escapeHtml(a.action)} <span class="src">${escapeHtml(a.supported_by || '')}</span></div>`;
  });

  if((report.assumptions_used || []).length){
    html += `<div class="section-title">Assumptions Used</div><ul class="assumptions">`;
    report.assumptions_used.forEach(a=> html += `<li>${escapeHtml(a)}</li>`);
    html += `</ul>`;
  }

  html += `<div class="section-title">QA Evaluation</div>`;
  if(evalr.scores){
    html += `<div class="score-grid">`;
    Object.entries(evalr.scores).forEach(([k,v])=>{
      html += `<div class="score-box"><div class="num">${v}/5</div><div>${prettyName(k)}</div></div>`;
    });
    html += `</div>`;
  }
  if(evalr.verdict){
    html += `<div class="verdict ${evalr.verdict}">${evalr.verdict}${data.revision_occurred ? ' (after 1 revision)' : ''}</div>`;
  }
  if((evalr.feedback || []).length){
    html += `<div class="section-title">Evaluator Feedback</div><ul class="assumptions">`;
    evalr.feedback.forEach(f=> html += `<li>${escapeHtml(f)}</li>`);
    html += `</ul>`;
  }

  el.innerHTML = html;
}
