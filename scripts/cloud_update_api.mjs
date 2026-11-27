// Anonymous, globally quota-limited manual updates. Provider credentials stay server-side.
const REPO = 'jimpakilove/linkdolls-dashboard';
const REPO_ID = 1212539757;
const OWNER_ID = 273734887;
const ORIGIN = 'https://jimpakilove.github.io';
const WORKFLOW = 'cloud-dashboard.yml';
const PUBLIC_STATUS = `${ORIGIN}/linkdolls-dashboard/landing-page-data/update-status.json`;
export const DAILY_LIMIT = 20;
export const dayKey = (time = Date.now()) => new Date(time + 8 * 3600000).toISOString().slice(0, 10);
const enc = new TextEncoder();
class ApiError extends Error {
  constructor(status, message, code = 'request_failed') { super(message); this.status=status; this.code=code; }
}
const b64 = bytes => btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
const encoded = data => b64(enc.encode(JSON.stringify(data)));
function der(tag, bytes) {
  const n=bytes.length, length=n<128?[n]:n<256?[129,n]:[130,n>>8,n&255];
  return Uint8Array.from([tag,...length,...bytes]);
}
export async function appJWT(env) {
  const pem=env.GITHUB_APP_PRIVATE_KEY;
  let bytes=Uint8Array.from(atob(pem.replace(/-----[^-]+-----|\s/g,'')),c=>c.charCodeAt(0));
  if (pem.includes('BEGIN RSA PRIVATE KEY')) {
    // Wrap GitHub's PKCS#1 download in PKCS#8 for WebCrypto; no temporary key file.
    bytes=der(48,Uint8Array.from([2,1,0,48,13,6,9,42,134,72,134,247,13,1,1,1,5,0,...der(4,bytes)]));
  }
  const key=await crypto.subtle.importKey('pkcs8',bytes,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  const now=Math.floor(Date.now()/1000);
  const content=encoded({alg:'RS256',typ:'JWT'})+'.'+encoded({iss:env.GITHUB_APP_ID,iat:now-60,exp:now+540});
  return content+'.'+b64(new Uint8Array(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,enc.encode(content))));
}
async function github(path, token, options={}) {
  let r;
  try {
    r=await fetch('https://api.github.com'+path,{...options,signal:AbortSignal.timeout(15000),headers:{
      Accept:'application/vnd.github+json',Authorization:'Bearer '+token,'X-GitHub-Api-Version':'2026-03-10',
      'Content-Type':'application/json','User-Agent':'LinkDolls-Dashboard-Control'}});
  } catch { throw new ApiError(502,'连接中断，提交结果待确认。请查看运行状态，勿重复提交。','connection_uncertain'); }
  if (r.status>=500) throw new ApiError(502,'更新服务暂时不可用，提交结果待确认。','connection_uncertain');
  if (!r.ok) throw new ApiError(502,`更新服务返回错误（${r.status}），请查看运行记录。`,'upstream_rejected');
  if (r.status===204) return null;
  try { return await r.json(); }
  catch { throw new ApiError(502,'提交结果待确认，请查看运行状态。','connection_uncertain'); }
}
let cached;
async function installationToken(env) {
  if (cached?.key===env.GITHUB_APP_PRIVATE_KEY && cached.installation===env.GITHUB_INSTALLATION_ID && cached.expires>Date.now()+60000) return cached.token;
  if (!/^\d+$/.test(env.GITHUB_INSTALLATION_ID)) throw new ApiError(503,'云端发布权限尚未配置。');
  const d=await github(`/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,await appJWT(env),{
    method:'POST',body:JSON.stringify({repository_ids:[REPO_ID],permissions:{actions:'write',metadata:'read'}})});
  if (!d.token || !Number.isFinite(Date.parse(d.expires_at))) throw new ApiError(503,'未能获取云端发布权限。');
  cached={key:env.GITHUB_APP_PRIVATE_KEY,installation:env.GITHUB_INSTALLATION_ID,token:d.token,expires:Date.parse(d.expires_at)};
  return d.token;
}
const stmt=(db,sql,...args)=>db.prepare(sql).bind(...args);
export async function quota(db) {
  const day=dayKey();
  const row=await stmt(db,'SELECT COALESCE(SUM(charged),0) AS used FROM update_requests WHERE day=?',day).first();
  return {day,timezone:'Asia/Shanghai',limit:DAILY_LIMIT,used:row.used,remaining:Math.max(0,DAILY_LIMIT-row.used)};
}
export async function reserve(db,id) {
  const time=Date.now(), day=dayKey(time);
  // ONE conditional INSERT on the primary database. No read-then-write counter.
  // The partial unique index is a second guard against concurrent active requests.
  return stmt(db,`INSERT OR IGNORE INTO update_requests
    (request_id,day,created_at,state,charged,next_poll)
    SELECT ?,?,?, 'reserved',1,?
    WHERE (SELECT COALESCE(SUM(charged),0) FROM update_requests WHERE day=?) < ?
      AND NOT EXISTS (SELECT 1 FROM update_requests WHERE state IN ('reserved','active','unknown'))
    RETURNING *`,id,day,time,time+30000,day,DAILY_LIMIT).first();
}
const openRequest=db=>stmt(db,"SELECT * FROM update_requests WHERE state IN ('reserved','active','unknown') LIMIT 1").first();
function publicRun(run) {
  return {id:run.id,status:run.status,conclusion:run.conclusion,
    url:`https://github.com/${REPO}/actions/runs/${run.id}`,started_at:run.created_at};
}
async function runResult(run) {
  const result={run:publicRun(run),published:false};
  if (run.status==='completed' && run.conclusion==='success') {
    try {
      const r=await fetch(`${PUBLIC_STATUS}?run=${run.id}`,{signal:AbortSignal.timeout(10000)});
      if (r.ok) {
        const d=await r.json();
        result.published=d.commit===run.head_sha && Date.parse(d.built_at)>=Date.parse(run.created_at);
        if (result.published) result.data_through=d.data_through;
      }
    } catch { /* Never equate a successful job with a confirmed public deployment. */ }
  }
  return result;
}
async function storeRun(db,id,run) {
  const result=await runResult(run);
  await stmt(db,'UPDATE update_requests SET state=?, run_id=?, result=?, next_poll=? WHERE request_id=?',
    run.status==='completed'?'done':'active',String(run.id),JSON.stringify(result),Date.now()+15000,id).run();
  return result;
}
async function runs(token) {
  const d=await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=main&per_page=50`,token);
  return d.workflow_runs;
}
export async function reconcile(env,row) {
  if (!row || row.state==='failed') return row;
  // Persistent poll lease avoids every visitor polling the provider independently.
  const claim=await stmt(env.DB,`UPDATE update_requests SET next_poll=? WHERE request_id=? AND next_poll<=?
    RETURNING request_id`,Date.now()+30000,row.request_id,Date.now()).first();
  if (!claim) return row;
  try {
    const token=await installationToken(env);
    let run;
    if (row.run_id) run=await github(`/repos/${REPO}/actions/runs/${row.run_id}`,token);
    else run=(await runs(token)).find(r=>r.display_title===`看板更新 · ${row.request_id}`);
    if (run) {
      if (run.head_branch!=='main' || run.path?.split('@')[0]!==`.github/workflows/${WORKFLOW}`)
        throw new Error('workflow identity mismatch');
      await storeRun(env.DB,row.request_id,run);
      return await stmt(env.DB,'SELECT * FROM update_requests WHERE request_id=?',row.request_id).first();
    }
  } catch { /* Keep the durable reservation on ambiguous or failed status checks. */ }
  return row;
}
function rowResult(row) {
  return {...(row?.result?JSON.parse(row.result):{run:null,published:false}),
    request_id:row?.request_id || null,waiting:!!row && ['reserved','unknown'].includes(row.state),
    failed:row?.state==='failed'};
}
async function body(request) {
  if (!request.headers.get('content-type')?.startsWith('application/json')) throw new ApiError(415,'请求格式错误。');
  const text=await request.text();
  if (text.length>1000) throw new ApiError(413,'请求过大。');
  let value;
  try { value=JSON.parse(text); } catch { throw new ApiError(400,'请求格式错误。'); }
  if (!value || typeof value!=='object' || Object.keys(value).length!==1 ||
      !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(value.request_id || ''))
    throw new ApiError(400,'仅允许有效的更新请求编号，不能指定仓库、分支或任务。');
  return value;
}
const ready=env=>!!(env.DB && env.GITHUB_APP_ID && env.GITHUB_INSTALLATION_ID && env.GITHUB_APP_PRIVATE_KEY);
async function route(request,env) {
  const url=new URL(request.url),path=url.pathname;
  if (path==='/health' && request.method==='GET') return {service:'dashboard-control',ready:ready(env),daily_limit:DAILY_LIMIT};
  if (!ready(env)) throw new ApiError(503,'免登录更新正在配置，当前请等待定时更新。','not_configured');
  if (path==='/updates' && request.method==='GET') {
    const requested=url.searchParams.get('request_id');
    const row=requested ? await stmt(env.DB,'SELECT * FROM update_requests WHERE request_id=?',requested).first() :
      await openRequest(env.DB) || await stmt(env.DB,'SELECT * FROM update_requests ORDER BY created_at DESC LIMIT 1').first();
    return {...rowResult(await reconcile(env,row)),quota:await quota(env.DB)};
  }
  if (path==='/updates' && request.method==='POST') {
    const {request_id:id}=await body(request);
    const old=await stmt(env.DB,'SELECT * FROM update_requests WHERE request_id=?',id).first();
    if (old) return {existing:true,...rowResult(await reconcile(env,old)),quota:await quota(env.DB)};
    const active=await openRequest(env.DB);
    if (active) {
      const current=await reconcile(env,active);
      if (current.state!=='done') return {existing:true,...rowResult(current),quota:await quota(env.DB)};
    }
    const reservation=await reserve(env.DB,id);
    if (!reservation) {
      const current=await openRequest(env.DB);
      if (current) return {existing:true,...rowResult(current),quota:await quota(env.DB)};
      const same=await stmt(env.DB,'SELECT * FROM update_requests WHERE request_id=?',id).first();
      if (same) return {existing:true,...rowResult(same),quota:await quota(env.DB)};
      throw new ApiError(429,'今日手动更新已达 20 次，北京时间明天零点恢复。','daily_limit');
    }
    let dispatched=false;
    try {
      const token=await installationToken(env);
      const repo=await github(`/repos/${REPO}`,token);
      if (repo.id!==REPO_ID || repo.owner?.id!==OWNER_ID) throw new Error('repository identity mismatch');
      const existing=(await runs(token)).find(r=>r.status!=='completed');
      if (existing) {
        // Joining a scheduled or already-running task consumes no manual quota.
        await storeRun(env.DB,id,existing);
        await stmt(env.DB,'UPDATE update_requests SET charged=0 WHERE request_id=?',id).run();
        return {existing:true,...rowResult(await stmt(env.DB,'SELECT * FROM update_requests WHERE request_id=?',id).first()),quota:await quota(env.DB)};
      }
      dispatched=true;
      const result=await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,token,{
        method:'POST',body:JSON.stringify({ref:'main',inputs:{dry_run:'false',request_id:id}})});
      const run=result?.workflow_run_id?{id:result.workflow_run_id,status:'queued',conclusion:null}:null;
      await stmt(env.DB,'UPDATE update_requests SET state=?, run_id=?, result=? WHERE request_id=?',
        run?'active':'unknown',run?String(run.id):null,JSON.stringify({run:run?publicRun(run):null,published:false}),id).run();
      return {accepted:true,request_id:id,run:run?publicRun(run):null,waiting:!run,published:false,quota:await quota(env.DB)};
    } catch(error) {
      // A timeout/crash must not silently refund a possibly dispatched request.
      const uncertain=dispatched && error.code!=='upstream_rejected';
      await stmt(env.DB,'UPDATE update_requests SET state=? WHERE request_id=?',uncertain?'unknown':'failed',id).run();
      if (uncertain) throw new ApiError(502,'提交结果待确认。已保留请求和次数，请查看运行状态。','connection_uncertain');
      throw error;
    }
  }
  throw new ApiError(404,'接口不存在。');
}
export default {
  async fetch(request,env) {
    const origin=request.headers.get('origin');
    const allowed=origin===ORIGIN || origin==='null' || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin || '');
    const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
      'X-Content-Type-Options':'nosniff','Vary':'Origin'};
    if (allowed) Object.assign(headers,{'Access-Control-Allow-Origin':origin,
      'Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'});
    try {
      if (new URL(request.url).pathname!=='/health' && !allowed) throw new ApiError(403,'请从看板页面使用更新功能。');
      if (request.method==='OPTIONS') return new Response(null,{status:204,headers});
      return new Response(JSON.stringify(await route(request,env)),{headers});
    } catch(error) {
      const safe=error instanceof ApiError?error:new ApiError(503,'更新服务暂时不可用，请稍后检查运行状态。');
      return new Response(JSON.stringify({error:safe.message,code:safe.code}),{status:safe.status,headers});
    }
  },
};
