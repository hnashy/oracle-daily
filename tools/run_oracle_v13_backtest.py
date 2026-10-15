#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,statistics,math,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from oracle_v13_engine import OracleV13,normalize_team,match_id
OUT=('h','d','a')
def fetch(url): return json.load(urllib.request.urlopen(url))
def parse_ts(s):
 if not s:return None
 s=str(s).replace(' UTC','Z').replace(' ','T');
 if not s.endswith('Z'):s+='Z'
 return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def odds_for(r):
 ko=parse_ts(r.get('match_date')); books=[]
 if ko is None:return None
 for b in r.get('1x2_market') or []:
  rows=b.get('odds_history_data') or []
  if len(rows)<3:continue
  vals=[]
  for row in rows[:3]:
   chosen=None
   op=row.get('opening_odds') or {}; ots=parse_ts(op.get('timestamp')); oo=float(op.get('odds') or 0)
   if ots is not None and ots<ko and oo>1:chosen=(ots,oo)
   for x in row.get('odds_history') or []:
    ts=parse_ts(x.get('timestamp'));v=float(x.get('odds') or 0)
    if ts is not None and ts<ko and v>1 and (chosen is None or ts>chosen[0]):chosen=(ts,v)
   if chosen is None:break
   vals.append(chosen)
  if len(vals)==3:books.append(vals)
 if not books:return None
 def med(i):return statistics.median(x[i][1] for x in books)
 return {'h':med(0),'d':med(1),'a':med(2),'bookmakers':len(books),'kickoff':ko,'quote_ts':max(x[i][0] for x in books for i in range(3))}
def key(date,h,a):return f'{date[:10]}|{normalize_team(h)}|{normalize_team(a)}'
def metrics(rows,k):
 if not rows:return {'n':0}
 b=l=hit=0
 for r in rows:
  p=r[k];o=r['outcome'];b+=sum((p[x]-(x==o))**2 for x in OUT);l-=math.log(max(p[o],1e-12));hit+=max(OUT,key=lambda x:p[x])==o
 return {'n':len(rows),'accuracy':hit/len(rows),'brier':b/len(rows),'logLoss':l/len(rows)}
def cal_error(rows,k):
 if not rows:return None
 bins=[]
 for i in range(5):
  rr=[r for r in rows if i/5<=max(r[k].values())<(i+1)/5]
  if rr:bins.append(abs(statistics.fmean(max(r[k].values()) for r in rr)-sum(max(r[k],key=r[k].get)==r['outcome'] for r in rr)/len(rr)))
 return statistics.fmean(bins) if bins else None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--raw',required=True);ap.add_argument('--out',required=True);ap.add_argument('--old',default='');args=ap.parse_args()
 raw=json.loads(Path(args.raw).read_text()); data=fetch('https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json')['matches']
 fixtures=[]
 for m in data:
  sc=m.get('score',{}).get('ft');
  if not sc or len(sc)!=2:continue
  fixtures.append({'date':m['date'],'time':m.get('time','15:00'),'h':m['team1'],'a':m['team2'],'gh':int(sc[0]),'ga':int(sc[1]),'ts':parse_ts(m['date']+' '+m.get('time','15:00'))})
 odds={}
 for r in raw:
  if r.get('match_date') and r.get('home_team') and r.get('away_team'):
   o=odds_for(r)
   if o:odds[key(r['match_date'],r['home_team'],r['away_team'])]=o
 eng=OracleV13();rows=[];history=[];quality={'raw':len(raw),'valid_kickoff':sum(bool(r.get('match_date')) for r in raw),'odds_valid':len(odds),'matched':0,'unmatched':[]}
 for m in sorted(fixtures,key=lambda x:x['ts']):
  k=key(m['date'],m['h'],m['a']);o=odds.get(k);p=eng.predict(m['h'],m['a'],m['ts'],o)
  if o:
   mw=.60
   if len(history)>=40:
    il=sum(-math.log(max(x['internal'][x['outcome']],1e-12)) for x in history)/len(history)
    ml=sum(-math.log(max(x['market'][x['outcome']],1e-12)) for x in history)/len(history)
    mw=.90 if ml<il else .60
   p['market_weight']=mw
   q={x:o[x]**-1 for x in OUT}; z=sum(q.values()); q={x:q[x]/z for x in OUT}
   p.update({x:(mw*q[x]+(1-mw)*p['internal'][x]) for x in OUT}); z=sum(p[x] for x in OUT); p.update({x:p[x]/z for x in OUT})
   quality['matched']+=1;rows.append({'id':match_id('en.1','2024-25',m['h'],m['a'],m['date']),'date':m['date'],'home':m['h'],'away':m['a'],'outcome':'h' if m['gh']>m['ga'] else 'a' if m['ga']>m['gh'] else 'd','model':{x:p[x] for x in OUT},'internal':p['internal'],'market':{x:1/o[x] for x in OUT},'odds':o})
   history.append(rows[-1])
  eng.update(m['h'],m['a'],m['gh'],m['ga'],m['ts'])
 quality['coverage_of_valid_kickoff']=quality['matched']/quality['valid_kickoff'] if quality['valid_kickoff'] else 0
 for r in rows:r['market']= {x:r['market'][x]/sum(r['market'].values()) for x in OUT}
 report={'generatedAt':datetime.now(timezone.utc).isoformat(),'version':'ORACLE v1.3','quality':quality,'metrics':{'v13':metrics(rows,'model'),'market':metrics(rows,'market'),'internal':metrics(rows,'internal'),'calibration_error_v13':cal_error(rows,'model'),'calibration_error_market':cal_error(rows,'market')},'rows':rows,'design':['advanced attack/defence Elo-like ratings','dynamic K with log(1+goal_difference)','league-specific HFA/rho/xi slots','Poisson Dixon-Coles draw mass','opponent-adjusted recent form','H2H capped at 5% context','40% internal / 60% market blend','strict chronological updates']}
 Path(args.out).parent.mkdir(parents=True,exist_ok=True);Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
