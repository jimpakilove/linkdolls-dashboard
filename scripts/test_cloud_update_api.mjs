import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {generateKeyPairSync,verify} from 'node:crypto';
import {readFileSync} from 'node:fs';
import api,{appJWT,dayKey,quota,reserve} from './cloud_update_api.mjs';

const origin='https://jimpakilove.github.io';
const pair=generateKeyPairSync('rsa',{modulusLength:2048});
const schema=readFileSync(new URL('./cloud_update_schema.sql',import.meta.url),'utf8');
function environment() {
  const sql=new DatabaseSync(':memory:');sql.exec(schema);
  const db={prepare(query) { return {bind(...args) {return {
    async first() { return sql.prepare(query).get(...args) || null; },
    async run() { return {meta:sql.prepare(query).run(...args)}; },
  };}};}};
  return {DB:db,sql,GITHUB_APP_ID:'test-app',GITHUB_INSTALLATION_ID:'123',
    GITHUB_APP_PRIVATE_KEY:pair.privateKey.export({type:'pkcs1',format:'pem'})};
}
const req=(body,source=origin,path='/updates')=>new Request('https://control.test'+path,{
  method:body===undefined?'GET':'POST',headers:{Origin:source,'Content-Type':'application/json'},
  ...(body===undefined?{}:{body:JSON.stringify(body)})});
function provider(t,options={}) {
  const posts=[];
  t.mock.method(globalThis,'fetch',async(url,init)=>{
    const u=String(url);
    if(u.includes('/access_tokens')) return Response.json({token:'provider-secret',expires_at:new Date(Date.now()+3600000).toISOString()});
    if(u.endsWith('/repos/jimpakilove/linkdolls-dashboard')) return Response.json({id:1212539757,owner:{id:273734887}});
    if(u.includes('/runs?')) return Response.json({workflow_runs:options.runs || []});
    if(u.endsWith('/dispatches')) {
      posts.push({url:u,body:JSON.parse(init.body)});
      if(options.timeout) throw new Error('lost response');
      return Response.json({workflow_run_id:456});
    }
    if(u.includes('/actions/runs/')) return Response.json({id:456,head_branch:'main',path:'.github/workflows/cloud-dashboard.yml',
      head_sha:'new',status:'completed',conclusion:'success',created_at:'2026-11-27T08:00:00Z'});
    if(u.includes('/update-status.json')) return Response.json({commit:options.published?'new':'old',built_at:'2026-11-27T09:00:00Z',data_through:'2026-11-22'});
    throw new Error('Unexpected provider URL '+u);
  });
  return posts;
}
test('Beijing midnight is the quota boundary, independent of machine timezone',()=>{
  assert.equal(dayKey(Date.parse('2026-11-27T15:59:59Z')),'2026-11-27');
  assert.equal(dayKey(Date.parse('2026-11-27T16:00:00Z')),'2026-11-28');
});
test('server app assertion signs correctly with GitHub PKCS1 key format',async()=>{
  const jwt=await appJWT(environment());const [a,b,s]=jwt.split('.');
  assert.equal(verify('RSA-SHA256',Buffer.from(a+'.'+b),pair.publicKey,Buffer.from(s,'base64url')),true);
  const payload=JSON.parse(Buffer.from(b,'base64url'));assert.equal(payload.iss,'test-app');
  assert.ok(payload.exp-payload.iat<=600);
});
test('anonymous update works but fixes repo, workflow and publication inputs',async(t)=>{
  const env=environment(),posts=provider(t),id=crypto.randomUUID();
  const r=await api.fetch(req({request_id:id}),env),data=await r.json();
  assert.equal(r.status,200);assert.equal(data.quota.remaining,19);assert.equal(data.run.id,456);
  assert.deepEqual(posts,[{url:'https://api.github.com/repos/jimpakilove/linkdolls-dashboard/actions/workflows/cloud-dashboard.yml/dispatches',
    body:{ref:'main',inputs:{dry_run:'false',request_id:id}}}]);
  assert.ok(!JSON.stringify(data).includes('provider-secret'));
});
test('global server limit rejects 21st request after 20 completed requests',async(t)=>{
  const env=environment(),posts=provider(t);
  for(let n=0;n<20;n++) {
    const r=await api.fetch(req({request_id:crypto.randomUUID()}),env);assert.equal(r.status,200);
    env.sql.exec("UPDATE update_requests SET state='done'");
  }
  const r=await api.fetch(req({request_id:crypto.randomUUID()}),env);
  assert.equal(r.status,429);assert.equal((await r.json()).code,'daily_limit');assert.equal(posts.length,20);
  assert.equal((await quota(env.DB)).remaining,0);
});
test('50 simultaneous independent callers create one reservation and one dispatch',async(t)=>{
  const env=environment(),posts=provider(t);
  const results=await Promise.all(Array.from({length:50},()=>api.fetch(req({request_id:crypto.randomUUID()}),env)));
  assert.ok(results.every(r=>r.status===200));assert.equal(posts.length,1);assert.equal((await quota(env.DB)).used,1);
});
test('same request stays idempotent even after completion and a new server instance',async(t)=>{
  const env=environment(),posts=provider(t),id=crypto.randomUUID();
  await api.fetch(req({request_id:id}),env);env.sql.exec("UPDATE update_requests SET state='done'");
  const r=await api.fetch(req({request_id:id}),{...env});
  assert.equal((await r.json()).existing,true);assert.equal(posts.length,1);assert.equal((await quota(env.DB)).used,1);
});
test('quota survives browser/server changes; yesterday does not consume today',async()=>{
  const env=environment();
  for(let i=0;i<20;i++) {
    await reserve(env.DB,crypto.randomUUID());env.sql.exec("UPDATE update_requests SET state='done'");
  }
  assert.equal(await reserve({...env.DB},crypto.randomUUID()),null);
  env.sql.exec("UPDATE update_requests SET day='2000-01-01'");
  assert.ok(await reserve({...env.DB},crypto.randomUUID()));assert.equal((await quota(env.DB)).used,1);
});
test('unknown dispatch result preserves quota and blocks a second dispatch',async(t)=>{
  const env=environment(),posts=provider(t,{timeout:true});
  const r=await api.fetch(req({request_id:crypto.randomUUID()}),env);
  assert.equal(r.status,502);assert.equal((await r.json()).code,'connection_uncertain');
  const next=await api.fetch(req({request_id:crypto.randomUUID()}),env);
  assert.equal((await next.json()).waiting,true);assert.equal(posts.length,1);
  assert.equal((await quota(env.DB)).used,1);
});
test('joining a scheduled run costs no manual quota and starts no job',async(t)=>{
  const env=environment(),posts=provider(t,{runs:[{id:789,status:'in_progress'}]});
  const r=await api.fetch(req({request_id:crypto.randomUUID()}),env),d=await r.json();
  assert.equal(d.existing,true);assert.equal(d.run.id,789);assert.equal(d.quota.used,0);assert.equal(posts.length,0);
});
test('wrong origin and arbitrary repo/branch parameters cannot dispatch',async(t)=>{
  const env=environment(),posts=provider(t);
  assert.equal((await api.fetch(req({request_id:crypto.randomUUID()},'https://untrusted.test'),env)).status,403);
  assert.equal((await api.fetch(req({request_id:crypto.randomUUID(),repo:'other'}),env)).status,400);
  assert.equal(posts.length,0);
});
test('readiness fails closed when durable quota store or cloud credentials are absent',async()=>{
  assert.equal((await api.fetch(req({request_id:crypto.randomUUID()}),{})).status,503);
  const health=await api.fetch(req(undefined,origin,'/health'),{});
  assert.equal((await health.json()).ready,false);
});
test('success requires matching public receipt; terminal status frees active slot',async(t)=>{
  const env=environment();provider(t);
  await api.fetch(req({request_id:crypto.randomUUID()}),env);
  env.sql.exec('UPDATE update_requests SET next_poll=0');
  const r=await api.fetch(req(),env),d=await r.json();
  assert.equal(d.run.conclusion,'success');assert.equal(d.published,false);
  assert.ok(await reserve(env.DB,crypto.randomUUID()));
});
test('matching live receipt reports publication confirmed',async(t)=>{
  const env=environment();provider(t,{published:true});
  await api.fetch(req({request_id:crypto.randomUUID()}),env);env.sql.exec('UPDATE update_requests SET next_poll=0');
  const d=await (await api.fetch(req(),env)).json();
  assert.equal(d.published,true);assert.equal(d.data_through,'2026-11-22');
});
