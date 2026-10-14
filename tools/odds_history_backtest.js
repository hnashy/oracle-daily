const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const RAW = process.argv[2] || path.join(ROOT, 'data/raw/epl_2024_2025_odds_history_sample.json');
const OUT = process.argv[3] || path.join(ROOT, 'reports/odds_backtest_epl_2024_25_sample.json');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const start = html.indexOf('const SEASONS=');
const end = html.indexOf('const S={', start);
let pure = html.slice(start, end);
pure = pure.replace('const ens=calculateEnsemblePrediction(eloP,dcP,w);', 'const ens=calculateEnsemblePrediction(eloP,dcP,w); if(globalThis.__oracleCapture)globalThis.__oracleCapture(m,eloP,dcP,ens);');
const factory = new Function(pure + '\nreturn {SEASONS,SRC,compact,walk,defaultParams,MODEL_VERSION};');
const { compact, walk, defaultParams, SRC, MODEL_VERSION } = factory();

const ALIASES = {
  'manchester utd': 'manchester united', 'newcastle utd': 'newcastle united',
  'leicester': 'leicester city', 'wolves': 'wolverhampton wanderers',
  'brighton': 'brighton hove albion', 'nottingham': 'nottingham forest',
  'ipswich': 'ipswich town', 'spurs': 'tottenham hotspur'
};
function teamKey(x) {
  let s = String(x || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/&/g, 'and').replace(/\b(afc|fc|cf|sc)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  return ALIASES[s] || s;
}
function dateKey(value) {
  const s = String(value || '');
  const m = s.match(/(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : '';
}
function parseUtc(value) {
  if (!value) return null;
  const s = String(value).replace(' UTC', 'Z').replace(' ', 'T');
  const t = Date.parse(s.endsWith('Z') || /[+-]\d\d:\d\d$/.test(s) ? s : s + 'Z');
  return Number.isFinite(t) ? t : null;
}
function median(xs) { const a = xs.filter(Number.isFinite).sort((x,y)=>x-y); return a.length ? a[Math.floor(a.length/2)] : null; }
function outcome(h, a) { return Number(h) > Number(a) ? 'h' : Number(h) < Number(a) ? 'a' : 'd'; }
function marketProb(odds) {
  const q = {h:1/odds.h, d:1/odds.d, a:1/odds.a};
  const z = q.h + q.d + q.a;
  return {h:q.h/z, d:q.d/z, a:q.a/z, overround:z-1};
}
function latestForBookmaker(book, kickoffTs) {
  const rows = book.odds_history_data || [];
  if (rows.length < 3) return null;
  const out = [];
  for (const row of rows.slice(0,3)) {
    let chosen = row.opening_odds && Number(row.opening_odds.odds) > 1 ? {ts:parseUtc(row.opening_odds.timestamp), odds:Number(row.opening_odds.odds)} : null;
    for (const point of (row.odds_history || [])) {
      const ts = parseUtc(point.timestamp), odds = Number(point.odds);
      if (ts !== null && ts < kickoffTs && odds > 1 && (!chosen || ts > chosen.ts)) chosen = {ts, odds};
    }
    if (!chosen || chosen.ts >= kickoffTs) return null;
    out.push(chosen);
  }
  return {odds:{h:out[0].odds,d:out[1].odds,a:out[2].odds}, ts:Math.max(...out.map(x=>x.ts))};
}
function extractMarket(record) {
  const kickoff = parseUtc(record.match_date);
  const books = [];
  for (const book of (record['1x2_market'] || [])) {
    const current = latestForBookmaker(book, kickoff);
    if (current) books.push(current);
  }
  if (!books.length) return null;
  const odds = {h:median(books.map(x=>x.odds.h)), d:median(books.map(x=>x.odds.d)), a:median(books.map(x=>x.odds.a))};
  if (![odds.h,odds.d,odds.a].every(x=>Number.isFinite(x) && x > 1)) return null;
  return {odds, market:marketProb(odds), scrapedTs:Math.max(...books.map(x=>x.ts)), bookmakers:books.length, kickoffTs:kickoff};
}
function key(date, h, a) { return `${date}|${teamKey(h)}|${teamKey(a)}`; }
function scoreMetrics(rows, pName) {
  const n=rows.length; if (!n) return {n:0};
  let brier=0, logLoss=0, hits=0;
  for (const r of rows) { const p=r[pName], o=r.outcome; brier += ['h','d','a'].reduce((z,k)=>z+Math.pow(p[k]-(o===k?1:0),2),0); logLoss -= Math.log(Math.max(p[o],1e-12)); if (['h','d','a'].sort((a,b)=>p[b]-p[a])[0]===o) hits++; }
  return {n, accuracy:hits/n, brier:brier/n, logLoss:logLoss/n};
}
function betting(rows, threshold) {
  const bets=[]; for (const r of rows) {
    const choices=['h','d','a'].map(k=>({k,ev:r.model[k]*r.odds[k]-1})).sort((a,b)=>b.ev-a.ev);
    const pick=choices[0]; if (pick.ev < threshold) continue;
    const won=r.outcome===pick.k; bets.push({ev:pick.ev, won, profit:won?r.odds[pick.k]-1:-1});
  }
  const stake=bets.length; return {threshold, bets:stake, hitRate:stake?bets.filter(x=>x.won).length/stake:0, roi:stake?bets.reduce((z,x)=>z+x.profit,0)/stake:0, totalProfit:bets.reduce((z,x)=>z+x.profit,0)};
}
async function main() {
  const raw=JSON.parse(fs.readFileSync(RAW,'utf8'));
  const [a,b] = await Promise.all(['2023-24','2024-25'].map(async season => {const r=await fetch(`${SRC}${season}/en.1.json`); if(!r.ok)throw new Error(`${r.status} ${season}`); return compact(await r.json(), season==='2023-24'?0:1);}));
  const all=[...a,...b].sort((x,y)=>x.ts-y.ts);
  const predictions=new Map();
  globalThis.__oracleCapture=(m,elo,dc,ens)=>{ if(m.gh===null || m.s<1)return; predictions.set(key(m.d,m.h,m.a),{model:{h:ens.h,d:ens.d,a:ens.a},elo:{h:elo.h,d:elo.d,a:elo.a},dc:{h:dc.h,d:dc.d,a:dc.a},outcome:outcome(m.gh,m.ga)}); };
  walk(all, Date.now(), 1, defaultParams());
  delete globalThis.__oracleCapture;
  const rows=[]; let droppedNoModel=0, droppedNoOdds=0;
  for (const r of raw) {
    const market=extractMarket(r); if(!market){droppedNoOdds++;continue;}
    const p=predictions.get(key(dateKey(r.match_date),r.home_team,r.away_team)); if(!p){droppedNoModel++;continue;}
    rows.push({...p,odds:market.odds,market:market.market,bookmakers:market.bookmakers,scrapedTs:market.scrapedTs,kickoffTs:market.kickoffTs,home:r.home_team,away:r.away_team,date:dateKey(r.match_date)});
  }
  const result={generatedAt:new Date().toISOString(),model:MODEL_VERSION,source:RAW,rawRecords:raw.length,matched:rows.length,droppedNoOdds,droppedNoModel,preKickoffQuotes:rows.every(r=>r.scrapedTs<r.kickoffTs),model:scoreMetrics(rows,'model'),market:scoreMetrics(rows,'market'),elo:scoreMetrics(rows,'elo'),dixonColes:scoreMetrics(rows,'dc'),betting:[0,0.05,0.10].map(t=>betting(rows,t)),bookmakerMedian:rows.length?median(rows.map(r=>r.bookmakers)):0,rows};
  fs.mkdirSync(path.dirname(OUT),{recursive:true}); fs.writeFileSync(OUT,JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({...result,rows:undefined},null,2));
}
main().catch(e=>{console.error(e);process.exit(1)});
