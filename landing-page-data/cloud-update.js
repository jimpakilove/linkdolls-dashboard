(() => {
  'use strict';
  if (document.getElementById('cloud-admin-dialog')) return;
  const API = 'https://linkdolls-dashboard-control.zhengwenxiu1010.chatgpt.site';
  const RUNS = 'https://github.com/jimpakilove/linkdolls-dashboard/actions/workflows/cloud-dashboard.yml';
  const PENDING = 'linkdolls.cloud-admin.pending';
  let timer, requestId = '', busy = false, awaiting = false, remaining = null;
  try { sessionStorage.removeItem('linkdolls.cloud-admin.session'); requestId = sessionStorage.getItem(PENDING) || ''; } catch {}
  const css = document.createElement('style');
  css.textContent = `
    .cloud-admin-controls{margin:14px;padding:12px;border:1px solid #3b4b63;border-radius:10px;flex-shrink:0}
    .cloud-admin-controls button{width:100%;background:#3b82f6;color:#fff;border:0;border-radius:7px;padding:10px;font:600 13px sans-serif;cursor:pointer}
    .cloud-admin-controls a{display:block;color:#b7c7dd;font:12px sans-serif;text-align:center;margin-top:10px;text-decoration:none}
    .cloud-admin-controls.cloud-admin-inline{background:#1e293b;display:flex;align-items:center;gap:16px;max-width:420px;margin:12px 16px}
    .cloud-admin-inline button{width:auto}.cloud-admin-inline a{margin:0}
    #cloud-admin-dialog{border:0;border-radius:16px;padding:24px;max-width:460px;width:calc(100% - 32px);color:#172338;box-shadow:0 20px 70px #0f172a40;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    #cloud-admin-dialog::backdrop{background:#0f172a66}#cloud-admin-dialog h2{margin:0;font-size:21px}
    #cloud-admin-dialog p{margin:12px 0;color:#526179}#cloud-admin-dialog button,#cloud-admin-dialog .cloud-admin-link{border-radius:8px;padding:9px 13px;border:1px solid #d7e0ec;background:white;font:inherit;cursor:pointer;text-decoration:none;display:inline-block}
    #cloud-admin-dialog button:disabled{cursor:wait;opacity:.55}#cloud-admin-dialog .cloud-admin-primary{background:#2563eb;color:white;border-color:#2563eb}
    #cloud-admin-dialog .cloud-admin-close{float:right;padding:3px 9px}#cloud-admin-dialog .cloud-admin-code{font:700 25px/1.5 ui-monospace,monospace;letter-spacing:2px;background:#edf3ff;padding:9px;border-radius:8px;text-align:center;user-select:all}
    #cloud-admin-dialog .cloud-admin-note{font-size:12px;color:#65748b}#cloud-admin-result{padding:12px;border-radius:9px;background:#f1f5fa;white-space:pre-line;margin:16px 0}
    #cloud-admin-dialog .cloud-admin-actions{display:flex;gap:9px;flex-wrap:wrap}#cloud-admin-dialog [hidden]{display:none!important}
  `;
  document.head.append(css);
  const panel = document.createElement('div');
  panel.className = 'cloud-admin-controls';
  panel.innerHTML = `<button type="button">☁ 云端更新</button><a href="${RUNS}" target="_blank" rel="noopener noreferrer">查看运行记录 ↗</a>`;
  const sidebar = document.querySelector('.sidebar');
  function placePanel() {
    if (sidebar && getComputedStyle(sidebar).display !== 'none') {
      panel.classList.remove('cloud-admin-inline');
      sidebar.insertBefore(panel, sidebar.querySelector('.sidebar-footer,.side-foot'));
    } else { panel.classList.add('cloud-admin-inline'); document.body.prepend(panel); }
  }
  placePanel(); window.addEventListener('resize', placePanel);
  const dialog = document.createElement('dialog');
  dialog.id = 'cloud-admin-dialog';
  dialog.setAttribute('aria-labelledby', 'cloud-admin-title');
  dialog.innerHTML = `
    <button type="button" class="cloud-admin-close" aria-label="关闭">×</button>
    <h2 id="cloud-admin-title">云端更新看板</h2>
    <p>读取云盘最新完整周的数据，检查通过后更新全部报表。电脑无需保持开机。</p>
    <div id="cloud-admin-quota" class="cloud-admin-note">正在读取今日剩余次数…</div>
    <div id="cloud-admin-result" role="status" aria-live="polite">无需登录，点击即可申请云端更新。</div>
    <div class="cloud-admin-actions">
      <button type="button" id="cloud-admin-start" class="cloud-admin-primary" disabled>开始更新</button>
      <button type="button" id="cloud-admin-check">检查运行状态</button>
      <button type="button" id="cloud-admin-reload" hidden>刷新报表</button>
    </div>
    <p class="cloud-admin-note">所有访问者共享每天 20 次手动更新额度，北京时间零点重置。失败申请也计次；重复点击同一任务不计次。定时更新不占此额度。</p>
    <p class="cloud-admin-note">请提前上传完整报表，并至少等待 5 分钟。更新可能需要十多分钟；关闭此窗口不会取消已启动的任务。</p>
    <a id="cloud-admin-run-link" href="${RUNS}" target="_blank" rel="noopener noreferrer">查看详细运行记录 ↗</a>`;
  document.body.append(dialog);
  const el = id => dialog.querySelector('#cloud-admin-' + id);
  const say = text => { el('result').textContent = text; };
  function save(key, value) { try { value ? sessionStorage.setItem(key, value) : sessionStorage.removeItem(key); } catch {} }
  function updateQuota(q) {
    remaining=q.remaining;
    el('quota').textContent=`今日已申请 ${q.used} / ${q.limit} 次 · 剩余 ${q.remaining} 次 · 北京时间`;
    el('start').disabled=busy || awaiting || remaining<=0;
  }
  async function call(path, data) {
    let response;
    try {
      response = await fetch(API + path, {method:data === undefined ? 'GET' : 'POST', mode:'cors', cache:'no-store',
        signal:AbortSignal.timeout(60000), headers:{'Content-Type':'application/json'},
        ...(data === undefined ? {} : {body:JSON.stringify(data)})});
    } catch { const error = new Error('连接暂时中断。请检查运行状态，避免重复启动。'); error.uncertain = true; throw error; }
    let result;
    try { result = await response.json(); } catch {
      const error = new Error('暂时无法确认接口返回结果。请检查运行状态，避免重复启动。');
      error.uncertain = data !== undefined; throw error;
    }
    if (!response.ok) {
      const error = new Error(result.error || '云端请求失败。'); error.uncertain = result.code === 'connection_uncertain'; throw error;
    }
    return result;
  }
  function later(fn, seconds) { clearTimeout(timer); if (dialog.open) timer=setTimeout(fn,seconds*1000); }
  async function check() {
    clearTimeout(timer);
    try {
      const query = requestId ? '?request_id='+encodeURIComponent(requestId) : '';
      const result = await call('/updates'+query);
      busy=!!result.run && result.run.status!=='completed';awaiting=result.waiting;
      updateQuota(result.quota);
      if (!result.run) {
        if (result.waiting) {
          say('提交结果正在确认，请勿重复提交。可以查看详细运行记录。');later(check,15);
        } else {
          requestId='';save(PENDING,'');
          say(result.failed?'上次申请未成功。请查看运行记录或稍后重试。':remaining<=0?'今日手动更新已达上限，北京时间明天零点恢复。':'无需登录，可以开始更新。');
        }
        return;
      }
      const run=result.run;el('run-link').href=run.url;
      requestId=result.request_id || '';save(PENDING,requestId);
      if (busy) {
        const label = run.status==='in_progress' ? '正在读取、检查和发布数据' : '任务已提交，正在排队';
        say(label+'。\n可以关闭窗口，任务仍会在云端继续。'); later(check,15);
      } else if (run.conclusion==='success' && result.published) {
        requestId='';save(PENDING,'');
        say(`更新成功，网站已确认发布。\n数据截至 ${result.data_through}。`);el('reload').hidden=false;
      } else if (run.conclusion==='success') {
        say('任务已完成，尚未确认网站版本更新，正在检查。');later(check,15);
      } else {
        requestId='';save(PENDING,'');
        say(`任务${run.conclusion==='cancelled'?'已取消':'未成功'}。请查看详细运行记录中的失败原因；补齐数据后可再次更新。`);
      }
    } catch(error) { say(error.message);el('quota').textContent='暂时无法读取今日额度';el('start').disabled=true;if (busy || awaiting) later(check,20); }
  }
  async function open() {
    dialog.showModal();el('reload').hidden=true;
    el('start').disabled=true;await check();
  }
  panel.querySelector('button').addEventListener('click',open);
  dialog.querySelector('.cloud-admin-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{clearTimeout(timer);});
  el('start').addEventListener('click',async()=>{
    if (busy || awaiting || remaining===null || remaining<=0) return;
    awaiting=true;el('start').disabled=true;el('reload').hidden=true;
    requestId=crypto.randomUUID();save(PENDING,requestId);say('正在提交更新请求…');
    try {
      const r=await call('/updates',{request_id:requestId});requestId=r.request_id || requestId;save(PENDING,requestId);
      updateQuota(r.quota);
      say(r.existing?'已有更新任务，正在查看进度。':'更新请求已提交，正在确认任务状态。');await check();
    } catch(error) {
      say(error.message);
      if (error.uncertain) { later(check,15); }
      else { awaiting=false;el('start').disabled=true;later(check,3); }
    }
  });
  el('check').addEventListener('click',check);
  el('reload').addEventListener('click',()=>location.reload());
  // The hosted page cannot call the Mac-only /api/refresh endpoint.
  if (location.hostname==='jimpakilove.github.io') {
    const refresh=document.getElementById('refreshBtn');
    if (refresh) { refresh.removeAttribute('onclick');refresh.addEventListener('click',open);
      const label=document.getElementById('refreshText');if(label) label.textContent='云端更新'; }
  }
})();
