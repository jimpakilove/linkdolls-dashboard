// Offline regression tests: execute rendering functions without a browser or network.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, 'dashboard_collection.html'), 'utf8');
const inline = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).find(s => s.includes('function renderSEOCard'));
const ctx = vm.createContext({console});
vm.runInContext(inline.split('/* 启动 */')[0], ctx);
const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'dashboard_detail.json'), 'utf8'));
const home = data.data['linkdolls.com']['w39_2026-09-21'];
function render(record) {
  ctx.input = record;
  return vm.runInContext('renderSEOCard(input)', ctx);
}
function value(output, label) {
  const start = output.indexOf(`<div class="kpi-label">${label}`);
  assert.ok(start >= 0, `Missing label: ${label}`);
  return output.slice(start).match(/<div class="kpi-value">([^<]*)<\/div>/)[1];
}
let out = render(home);
for (const [label, expected] of Object.entries({'页面浏览':'1,402','访问次数':'973','访问用户':'906','GSC点击':'574','跳出率':'27.4%','每次访问浏览':'11.74','平均时长':'4:51','移动端占比':'—'})) {
  assert.equal(value(out, label), expected);
}
assert.ok(out.includes('重新导出'));
const w40 = data.data['linkdolls.com']['w40_2026-09-28'];
for (const [label, expected] of Object.entries({'页面浏览':'1,457','访问次数':'1,006','访问用户':'927','GSC点击':'485','跳出率':'31.9%','每次访问浏览':'6.72','平均时长':'3:59','移动端占比':'—'})) {
  assert.equal(value(render(w40), label), expected, `W40 ${label}`);
}
for (const ga4 of [{available:false,pageviews:0}, {available:false,pageviews:100}, {pageviews:0}, {}]) {
  ctx.input = {...home, ga4};
  assert.equal(vm.runInContext('clickRate(input, 10)', ctx), '—');
  const clickCard = vm.runInContext('renderClickCard(input)', ctx);
  assert.ok(!clickCard.includes('NaN') && !clickCard.includes('Infinity') && !clickCard.includes('浏览(1)'));
}
ctx.input = {ga4:{available:true,pageviews:1000}};
assert.equal(vm.runInContext('clickRate(input, 10, 2)', ctx), '1.00%');
const missing = structuredClone(home);
missing.landingPage = {available:false,reason:'缺少该周着陆页访问表'};
assert.equal(value(render(missing), '访问次数'), '—');
missing.landingPage = {available:true,sessions:0,visitors:0,bounceRate:0,avgSessionDuration:0,pageviewsPerSession:0};
assert.equal(value(render(missing), '访问次数'), '0');
assert.equal(value(render(missing), '跳出率'), '0.0%');
missing.landingPage.sessions = null;
assert.equal(value(render(missing), '访问次数'), '—');
missing.deviceStatus = {available:true};
assert.equal(value(render(missing), '移动端占比'), '83%');
missing.devices = [{device:'desktop',clicks:10}];
assert.equal(value(render(missing), '移动端占比'), '0%');
missing.devices = [{device:'mobile',clicks:0}];
assert.equal(value(render(missing), '移动端占比'), '—');
ctx.fixture = {data:{test:{a:home,b:{...home,landingPage:{available:false,reason:'缺少访问表'}}}}};
const partial = vm.runInContext("RAW=fixture;currentCat='test';aggregateWeeks(['a','b'])", ctx);
assert.equal(partial.landingPage.sessions, null);
assert.equal(value(render(partial), '访问次数'), '—');
ctx.fixture = {data:{test:{a:home,b:home}}};
const complete = vm.runInContext("RAW=fixture;aggregateWeeks(['a','b'])", ctx);
assert.equal(complete.landingPage.sessions, 1946);
assert.equal(complete.deviceStatus.available, false);
assert.equal(complete.gsc.clicks, 1148);
// The cart table must distinguish corrupt exports, genuine zero, and partial periods.
const cartElement = {innerHTML: ''};
ctx.document = {getElementById: id => id === 'cartTable' ? cartElement : null};
ctx.input = data.data['sex-doll-head']['w30_2026-07-20'];
vm.runInContext('renderTables(input)', ctx);
assert.ok(cartElement.innerHTML.includes('编码损坏'));
assert.ok(cartElement.innerHTML.includes('sex-doll-head/w30_2026-07-20/'));
assert.ok(!cartElement.innerHTML.includes('暂无加购数据'));
ctx.input = {...home, cartAdds: [], cartStatus: {available:true}};
vm.runInContext('renderTables(input)', ctx);
assert.ok(cartElement.innerHTML.includes('没有加购次数大于 0'));
ctx.fixture = {data:{test:{a:home,b:data.data['sex-doll-head']['w30_2026-07-20']}}};
ctx.input = vm.runInContext("RAW=fixture;currentCat='test';aggregateWeeks(['a','b'])", ctx);
assert.equal(ctx.input.cartStatus.available, false);
vm.runInContext('renderTables(input)', ctx);
assert.ok(cartElement.innerHTML.includes('编码损坏'));
let count = 0;
for (const weeks of Object.values(data.data)) {
  for (const record of Object.values(weeks)) {
    ctx.input = record;
    const output = vm.runInContext('renderSEOCard(input) + renderGSCCard(input)', ctx);
    assert.ok(!output.includes('NaN') && !output.includes('undefined'));
    count++;
  }
}
console.log(`PASS: homepage values, missing vs zero, device scope, partial/complete periods, ${count} weekly records rendered offline`);
