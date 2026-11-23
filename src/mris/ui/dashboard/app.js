/* RiskLens AI: dependency-free browser client for the local FastAPI application. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { mode: 'scrape', view: 'overview', data: null, selected: 0, selectedPage: 0, preview: 'text', loading: false };
  const headings = {
    overview: ['Overview', 'Intelligence overview', 'Scrape merchant websites, inspect page content, and review risk signals from one workspace.'],
    scraper: ['Web Scraper', 'Web scraping studio', 'Extract homepage content, linked policies, HTML, readable text and JavaScript references.'],
    assessment: ['Risk Assessment', 'Merchant risk assessment', 'Run the existing MRIS classification and human-review routing pipeline.']
  };
  function esc(x) { return String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
  function formatNumber(v) { return typeof v === 'number' ? new Intl.NumberFormat().format(v) : '—'; }
  function setMessage(text, good = false) { const el = $('message'); el.textContent = text; el.classList.remove('hidden'); el.classList.toggle('good', good); }
  function clearMessage() { $('message').classList.add('hidden'); }
  function setView(view) {
    state.view = view;
    const [crumb, title, sub] = headings[view];
    $('breadName').textContent = crumb; $('pageTitle').innerHTML = esc(title) + '<span class="title-period">.</span>'; $('pageSubtitle').textContent = sub;
    document.querySelectorAll('.nav-item[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    if (view === 'scraper' || view === 'assessment') { setMode(view === 'scraper' ? 'scrape' : 'assess'); $('inputPanel').scrollIntoView({behavior:'smooth', block:'start'}); }
    else window.scrollTo({top:0, behavior:'smooth'});
  }
  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll('.mode').forEach(b => { b.classList.toggle('active', b.dataset.mode === mode); b.setAttribute('aria-selected', String(b.dataset.mode === mode)); });
    $('inputHeading').textContent = mode === 'scrape' ? 'Start a web scraping run' : 'Start a risk assessment';
    $('scrapeOptions').classList.toggle('hidden', mode !== 'scrape');
    $('runLabel').textContent = mode === 'scrape' ? 'Run web scraper' : 'Assess merchants';
    $('runLimit').textContent = mode === 'scrape' ? 'Maximum 250 URLs per scraping request' : 'Maximum 20,000 URLs per assessment request';
    clearMessage();
  }
  function enteredUrls() {
    const urls = $('urlInput').value.split(/[\r\n]+/).map(x => x.trim()).filter(Boolean);
    return [...new Set(urls)];
  }
  function updateUrlCount() { $('urlCount').textContent = `${enteredUrls().length.toLocaleString()} entered`; }
  // Parse quoted CSV, including commas/newlines inside quoted fields.
  function parseCsv(text) {
    const rows = []; let row = [], cell = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (ch === '"') { if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted; }
      else if (ch === ',' && !quoted) { row.push(cell); cell = ''; }
      else if ((ch === '\n' || ch === '\r') && !quoted) { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); if (row.some(v => v.trim())) rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    row.push(cell); if (row.some(v => v.trim())) rows.push(row);
    return rows;
  }
  async function importFile(file) {
    if (!file || !/\.(txt|csv)$/i.test(file.name)) { setMessage('Choose a CSV or TXT file.'); return; }
    if (file.size > 2_000_000) { setMessage('Files must be smaller than 2 MB for the interactive UI.'); return; }
    const text = (await file.text()).replace(/^\uFEFF/, '');
    let urls = [];
    if (/\.csv$/i.test(file.name)) {
      const rows = parseCsv(text); const heads = (rows[0] || []).map(x => x.trim().toLowerCase());
      const index = heads.findIndex(h => ['url', 'website', 'website_url', 'domain', 'merchant_url'].includes(h));
      const column = index >= 0 ? index : 0; urls = rows.slice(index >= 0 ? 1 : 0).map(r => (r[column] || '').trim()).filter(Boolean);
    } else urls = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    const combined = [...new Set([...enteredUrls(), ...urls])];
    $('urlInput').value = combined.join('\n'); updateUrlCount();
    setMessage(`Imported ${urls.length.toLocaleString()} URLs from ${file.name}. ${combined.length.toLocaleString()} unique entries ready.`, true);
  }
  function badge(status) {
    const cls = status === 'ok' || status === 'NO_HUMAN_REVIEW' ? '' : status === 'limited_content' ? 'warn' : 'bad';
    const label = {ok:'OK', limited_content:'LIMITED', NO_HUMAN_REVIEW:'NO REVIEW', HUMAN_REVIEW:'REVIEW'}[status] || String(status || 'ERROR').replaceAll('_',' ').toUpperCase();
    return `<span class="chip ${cls}">${esc(label)}</span>`;
  }
  async function run() {
    if (state.loading) return;
    const urls = enteredUrls();
    if (!urls.length) { setMessage('Please enter at least one website URL first.'); $('urlInput').focus(); return; }
    const max = state.mode === 'scrape' ? 250 : 20000;
    if (urls.length > max) { setMessage(`The ${state.mode} endpoint accepts at most ${max.toLocaleString()} URLs per request. Please split this run.`); return; }
    state.loading = true; clearMessage(); $('runButton').disabled = true; $('runArrow').classList.add('hidden'); $('spinner').classList.remove('hidden');
    $('runLabel').textContent = 'Processing...';
    try {
      const body = state.mode === 'scrape' ? { urls, include_html:$('includeHtml').checked, include_inline_scripts:$('includeScripts').checked, fetch_external_scripts:$('fetchExternalScripts').checked } : { urls };
      const response = await fetch(state.mode === 'scrape' ? '/scrape' : '/assess', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      let payload;
      try { payload = await response.json(); } catch { throw new Error(`Server returned HTTP ${response.status}.`); }
      if (!response.ok) { const detail = payload.detail; throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || `HTTP ${response.status}`)); }
      state.data = payload; state.dataMode = state.mode; state.selected = 0; state.selectedPage = 0; state.preview = 'text';
      $('filterInput').value = ''; $('statusFilter').value = 'all';
      renderData();
      if (state.dataMode === 'scrape' && payload.count > 0 && payload.successful === 0 && payload.limited === 0) {
        const unavailable = payload.results.filter(s => s.fetch_status === 'robots_unavailable').length;
        const blocked = payload.results.filter(s => s.fetch_status === 'blocked').length;
        setMessage(`No pages retrieved. ${unavailable} robots.txt checks unavailable; ${blocked} explicitly blocked or access denied. Inspect a site's error message. See docs/ROBOTS_TROUBLESHOOTING.md and run scripts/diagnose_access.py for more details.`);
      } else {
        setMessage(`Completed ${payload.count} sites in ${payload.elapsed_seconds} seconds.`, true);
      }
      $('outputPanel').scrollIntoView({behavior:'smooth', block:'start'});
    } catch (error) { setMessage(`Run failed: ${error.message}. Ensure the API is running and try again.`); }
    finally { state.loading = false; $('runButton').disabled = false; $('spinner').classList.add('hidden'); $('runArrow').classList.remove('hidden'); $('runLabel').textContent = state.mode === 'scrape' ? 'Run web scraper' : 'Assess merchants'; }
  }
  function renderData() {
    const data = state.data; if (!data) return;
    $('emptyState').classList.add('hidden'); $('resultsBody').classList.remove('hidden'); $('downloadJson').disabled = false; $('downloadCsv').disabled = false;
    $('resultCount').textContent = data.count.toLocaleString();
    const alert = $('resultsAlert');
    if (state.dataMode === 'scrape' && data.count > 0 && data.successful === 0 && data.limited === 0) {
      const unavailable = data.results.filter(s => s.fetch_status === 'robots_unavailable').length;
      const blocked = data.results.filter(s => s.fetch_status === 'blocked').length;
      alert.textContent = `No pages retrieved: ${unavailable} robots.txt checks unavailable, ${blocked} blocked/access denied, ${data.failed - unavailable - blocked} other errors. Select a website to inspect its exact reason. See docs/ROBOTS_TROUBLESHOOTING.md.`;
      alert.classList.remove('hidden');
    } else {
      alert.textContent = '';
      alert.classList.add('hidden');
    }
    const pages = state.dataMode === 'scrape' ? data.total_pages : '—';
    const scripts = state.dataMode === 'scrape' ? data.results.reduce((a, site) => a + site.pages.reduce((s,p) => s + p.script_count,0),0) : '—';
    $('statSites').textContent = formatNumber(data.count); $('statPages').textContent = formatNumber(pages); $('statScripts').textContent = formatNumber(scripts);
    $('statTime').textContent = `${data.elapsed_seconds}s`;
    $('resultsSubtitle').textContent = state.dataMode === 'scrape' ? `${data.successful} successful • ${data.limited} limited • ${data.failed} failed` : 'Risk classification, review decisions and supporting reasons';
    renderSiteList();
  }
  function getStatus(site) { return state.dataMode === 'scrape' ? site.fetch_status : site.routing_decision; }
  function renderSiteList() {
    const all = state.data.results; const filter = $('filterInput').value.toLowerCase().trim(); const status = $('statusFilter').value;
    const indices = all.map((site, i) => ({site,i})).filter(({site}) => {
      const match = !filter || site.url.toLowerCase().includes(filter);
      if (state.dataMode !== 'scrape') return match && (status === 'all' || (status === 'ok' ? site.routing_decision === 'NO_HUMAN_REVIEW' : status === 'failed' ? site.routing_decision === 'HUMAN_REVIEW' : true));
      return match && (status === 'all' || (status === 'failed' ? !['ok','limited_content'].includes(site.fetch_status) : site.fetch_status === status));
    });
    if (indices.length && !indices.some(x => x.i === state.selected)) { state.selected = indices[0].i; state.selectedPage = 0; }
    $('siteList').innerHTML = indices.length ? indices.map(({site,i}) => `<button class="site-card ${i === state.selected ? 'active' : ''}" data-index="${i}"><span class="domain">${esc(site.domain || site.url)}</span><small>${esc(site.url)}</small><span class="chip-line">${badge(getStatus(site))}<small>${state.dataMode === 'scrape' ? site.pages_found + ' pages' : site.review_reasons.length + ' reasons'}</small></span></button>`).join('') : '<p class="muted">No websites match this filter.</p>';
    $('siteList').querySelectorAll('[data-index]').forEach(btn => btn.addEventListener('click', () => { state.selected = Number(btn.dataset.index); state.selectedPage = 0; state.preview = 'text'; renderSiteList(); }));
    $('siteDetail').innerHTML = indices.length ? detailHtml(all[state.selected]) : '<p class="muted">Adjust filters to inspect a website.</p>';
    bindDetail();
  }
  function detailHtml(site) { return state.dataMode === 'scrape' ? scrapeDetail(site) : assessDetail(site); }
  function scrapeDetail(site) {
    const page = site.pages[state.selectedPage];
    const title = `<div class="detail-title">${esc(site.domain)}</div><div class="detail-meta">${esc(site.url)}</div><p>${badge(site.fetch_status)} <span class="muted">&nbsp;${site.elapsed_seconds}s • ${site.pages_found} pages</span></p>`;
    if (!page) return title + `<p class="muted">No pages were retrieved. ${esc(site.error || '')}</p>`;
    let content = '';
    if (state.preview === 'text') content = `<pre class="data-preview">${esc(page.text || '(No visible text)')}${page.text_truncated ? '\n… [truncated]' : ''}</pre>`;
    else if (state.preview === 'html') content = `<pre class="data-preview">${esc(page.html === null ? 'HTML was not included in this run. Enable the HTML preview option before scraping.' : page.html)}${page.html_truncated ? '\n… [truncated]' : ''}</pre>`;
    else content = page.scripts.length ? `<div class="data-preview">${page.scripts.map(s => `<div class="script-entry"><b>${s.inline ? 'Inline JavaScript' : s.fetched ? 'External script (fetched)' : 'External script (URL only)'}</b><div><code>${esc(s.src || '(inline)')}</code></div><small class="muted">Type: ${esc(s.type)}</small>${s.content ? `<pre>${esc(s.content)}${s.truncated ? '\n… [truncated]' : ''}</pre>` : ''}</div>`).join('')}</div>` : `<pre class="data-preview">No script elements detected on this page.</pre>`;
    return title + `<div class="page-selector">${site.pages.map((p,i) => `<button data-page="${i}" class="${state.selectedPage === i ? 'active' : ''}">${esc(p.page_type)}</button>`).join('')}</div><div class="detail-meta">${esc(page.title || page.url)} • ${page.script_count} scripts</div><div class="code-tabs">${['text','html','scripts'].map(t => `<button data-preview="${t}" class="${state.preview === t ? 'active' : ''}">${t === 'text' ? 'Visible text' : t === 'html' ? 'HTML source' : 'Scripts'}</button>`).join('')}</div>${content}`;
  }
  function assessDetail(site) {
    const flags = Object.entries(site.risk_flags || {}).filter(([,flag]) => flag).map(([name]) => name.replaceAll('_',' '));
    return `<div class="detail-title">${esc(site.url)}</div><p>${badge(site.routing_decision)}</p><div class="assessment-fields"><div><small>Industry</small><strong>${esc(site.industry_classification?.description || 'Not determined')}</strong></div><div><small>MCC / NAICS</small><strong>${esc(site.industry_classification?.mcc || '—')} / ${esc(site.industry_classification?.naics || '—')}</strong></div><div><small>Checkout detected</small><strong>${site.has_working_checkout ? 'Yes' : 'No'}</strong></div><div><small>Fetch status</small><strong>${esc(site.fetch_status)}</strong></div></div><h3>Flagged signals</h3>${flags.length ? `<ul class="reasons">${flags.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>` : '<p class="muted">No risk flags detected.</p>'}<h3>Review reasons</h3>${site.review_reasons.length ? `<ul class="reasons">${site.review_reasons.map(s => `<li>${esc(s)}</li>`).join('')}</ul>` : '<p class="muted">No review reasons.</p>'}`;
  }
  function bindDetail() {
    $('siteDetail').querySelectorAll('[data-page]').forEach(b => b.addEventListener('click', () => { state.selectedPage = Number(b.dataset.page); state.preview = 'text'; renderSiteList(); }));
    $('siteDetail').querySelectorAll('[data-preview]').forEach(b => b.addEventListener('click', () => { state.preview = b.dataset.preview; renderSiteList(); }));
  }
  function download(name, content, type) { const blob = new Blob([content], {type}); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  function csvCell(value) { return `"${String(value ?? '').replaceAll('"','""')}"`; }
  function exportCsv() {
    if (!state.data) return;
    const fields = state.dataMode === 'scrape' ? ['url','domain','fetch_status','elapsed_seconds','pages_found','page_types','scripts_found','error'] : ['url','routing_decision','fetch_status','industry','mcc','naics','risk_flags','review_reasons'];
    const rows = state.data.results.map(s => state.dataMode === 'scrape' ? [s.url,s.domain,s.fetch_status,s.elapsed_seconds,s.pages_found,s.pages.map(p=>p.page_type).join('; '),s.pages.reduce((n,p)=>n+p.script_count,0),s.error] : [s.url,s.routing_decision,s.fetch_status,s.industry_classification?.description,s.industry_classification?.mcc,s.industry_classification?.naics,Object.entries(s.risk_flags).filter(([,v])=>v).map(([k])=>k).join('; '),s.review_reasons.join('; ')]);
    download('mris_'+state.dataMode+'_results.csv', [fields,...rows].map(r=>r.map(csvCell).join(',')).join('\r\n'),'text/csv;charset=utf-8');
  }
  document.querySelectorAll('.nav-item[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  document.querySelectorAll('.mode').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
  $('quickStart').addEventListener('click', () => setView('scraper')); $('emptyStart').addEventListener('click', () => $('urlInput').focus());
  $('urlInput').addEventListener('input', updateUrlCount); $('clearUrls').addEventListener('click', () => { $('urlInput').value = ''; updateUrlCount(); clearMessage(); });
  $('fileInput').addEventListener('change', async e => { if (e.target.files[0]) await importFile(e.target.files[0]); e.target.value = ''; });
  const drop = $('dropzone'); ['dragenter','dragover'].forEach(name => drop.addEventListener(name, e=>{ e.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave','drop'].forEach(name => drop.addEventListener(name, e=>{ e.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', async e => { if(e.dataTransfer.files[0]) await importFile(e.dataTransfer.files[0]); });
  $('runButton').addEventListener('click', run); $('filterInput').addEventListener('input', renderSiteList); $('statusFilter').addEventListener('change', renderSiteList);
  $('downloadJson').addEventListener('click', () => state.data && download('mris_'+state.dataMode+'_results.json', JSON.stringify(state.data,null,2),'application/json'));
  $('downloadCsv').addEventListener('click', exportCsv);
  $('today').textContent = new Date().toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
  fetch('/health').then(r=>{if(!r.ok) throw Error('Health check failed');return r.json();}).then(()=>$('healthText').textContent='API connected').catch(()=>{$('healthText').textContent='API offline';document.querySelector('.connection').classList.add('off');});
  updateUrlCount();
})();
