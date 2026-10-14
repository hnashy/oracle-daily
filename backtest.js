const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const start = html.indexOf("const SEASONS=");
const end = html.indexOf("const S={", start);
if (start < 0 || end < 0) throw new Error('لم يتم العثور على كود النموذج');
const pure = html.slice(start, end);
const factory = new Function(pure + '\nreturn {SEASONS, SRC, compact, walk, defaultParams, MODEL_VERSION};');
const {SEASONS, SRC, compact, walk, defaultParams, MODEL_VERSION} = factory();
const leagues = ['en.1','de.1','es.1','it.1','fr.1'];

async function load(i, league) {
  const u = SRC + SEASONS[i] + '/' + league + '.json';
  const r = await fetch(u);
  if (!r.ok) throw new Error(`${r.status} ${u}`);
  return compact(await r.json(), i);
}
function pct(x) { return (100*x).toFixed(2)+'%'; }
function row(name, st) {
  if (!st || !st.n) return {name, n:0};
  const homeRate=st.home/st.n, brierHome=2*(1-homeRate);
  return {name, n:st.n, accuracy:st.hit/st.n, brier:st.brier, logLoss:st.logLoss,
    bssHome:1-st.brier/brierHome, bssUniform:1-st.brier/(2/3), homeRate};
}
(async()=>{
  const output={model:MODEL_VERSION, generatedAt:new Date().toISOString(), seasons:SEASONS, results:[]};
  for (const league of leagues) {
    const parts = await Promise.all(SEASONS.map((_,i)=>load(i,league).catch(()=>[])));
    const all = parts.flat().sort((a,b)=>a.ts-b.ts);
    const first = all.length ? all[0].s : 0;
    const maxTs = Date.now();
    const cur = Math.max(...all.map(x=>x.s));
    const full = walk(all, maxTs, Math.max(first+1, 0), defaultParams());
    const app = walk(all, maxTs, Math.max(first+1, cur-1), defaultParams());
    output.results.push({league, matchesLoaded:all.length, seasonsLoaded:[...new Set(all.map(x=>x.s))],
      fullWindow:{fromSeason:Math.max(first+1,0), evaluated:{
        ensemble:row('Ensemble',full.enM), elo:row('Elo',full.eloM), dixonColes:row('Dixon-Coles',full.dcM)}, weights:full.w, rho:full.rho},
      appWindow:{fromSeason:Math.max(first+1,cur-1), evaluated:{
        ensemble:row('Ensemble',app.enM), elo:row('Elo',app.eloM), dixonColes:row('Dixon-Coles',app.dcM)}, weights:app.w, rho:app.rho}});
  }
  console.log(JSON.stringify(output,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
