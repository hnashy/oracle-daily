"""ORACLE v1.3: chronological football probability engine.

No future results are read before a prediction. Market blending is explicit,
news inputs are optional and conservative, and all secondary features are
bounded corrections rather than replacements for the goal model.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict, deque
from math import exp, log, factorial
from typing import Dict, List, Optional, Tuple

OUT=('h','d','a')
ALIASES={
 'man utd':'manchester united','manchester utd':'manchester united','manchester united':'manchester united',
 'newcastle':'newcastle united','leicester':'leicester city','wolves':'wolverhampton wanderers',
 'brighton':'brighton hove albion','nottingham':'nottingham forest','ipswich':'ipswich town',
 'tottenham':'tottenham hotspur','west ham':'west ham united','bournemouth':'bournemouth',
}
def normalize_team(s):
 s=str(s or '').lower().replace('&','and')
 for x in ('afc ',' fc',' cf',' sc'): s=s.replace(x,' ')
 s=' '.join(''.join(c if c.isalnum() or c==' ' else ' ' for c in s).split())
 return ALIASES.get(s,s)
def match_id(league,season,home,away,kickoff):
 return '|'.join((str(league),str(season),normalize_team(home),normalize_team(away),str(kickoff)[:10]))
def poisson(k,l): return exp(-l)*l**k/factorial(k)
def norm(p):
 z=sum(p.values()) or 1
 return {k:max(1e-9,p[k]/z) for k in OUT}
def outcome(h,a): return 'h' if h>a else 'a' if a>h else 'd'
@dataclass
class Team:
 attack:float=1.0
 defence:float=1.0
 home:float=0.0
 away:float=0.0
 last:int=0
 played:int=0
 points:float=0.0
 recent:deque=field(default_factory=lambda:deque(maxlen=5))
@dataclass
class League:
 home_goals:float=1.45
 away_goals:float=1.15
 hfa:float=0.12
 rho:float=-0.08
 xi:float=0.006
 played:int=0

class OracleV13:
 def __init__(self, league='en.1', season='2024-25'):
  self.league=league; self.season=season; self.teams=defaultdict(Team); self.leagues=defaultdict(League); self.history=[]
 def _team(self,n): return self.teams[normalize_team(n)]
 def _league(self): return self.leagues[self.league]
 def _decay(self,t,ts):
  if not t.last:return
  days=max(0,(ts-t.last)/86400)
  f=exp(-log(2)*days/180)
  t.attack=1+(t.attack-1)*f; t.defence=1+(t.defence-1)*f
 def _lambdas(self,h,a,ts):
  L=self._league(); ht,at=self._team(h),self._team(a); self._decay(ht,ts);self._decay(at,ts)
  # regularized attack/defence with bounded home/away ratings
  lh=max(.15,min(4.5,L.home_goals*ht.attack*at.defence*exp(max(-.25,min(.25,ht.home)))))
  la=max(.12,min(4.2,L.away_goals*at.attack*ht.defence*exp(max(-.25,min(.25,at.away)))))
  return lh,la
 def _context(self,h,a,ts):
  ht,at=self._team(h),self._team(a)
  # recent, opponent-adjusted, venue-aware form; max correction is deliberately small
  def form(t):
   if not t.recent:return 0.0
   return sum(x['signal']*x['weight'] for x in t.recent)/sum(x['weight'] for x in t.recent)
  signal=max(-1,min(1,.65*(form(ht)-form(at))+.35*(at.points-ht.points)/max(10,self._league().played)))
  h2h=[x for x in self.history if x['ts']<ts and {x['h'],x['a']}=={normalize_team(h),normalize_team(a)}][-5:]
  h2h_signal=0
  if len(h2h)>=3:
   z=sum(.82**i for i in range(len(h2h)))
   h2h_signal=sum((1 if ((x['h']==normalize_team(h) and x['gh']>x['ga']) or (x['a']==normalize_team(h) and x['ga']>x['gh'])) else 0 if x['gh']==x['ga'] else -1)*.82**i for i,x in enumerate(reversed(h2h)))/z
  return max(-1,min(1,.60*signal+.05*h2h_signal))
 def _dc(self,lh,la,rho):
  ph=[poisson(i,lh) for i in range(9)];pa=[poisson(i,la) for i in range(9)]; raw=[]
  for x in range(9):
   for y in range(9):
    tau=1
    if x==0 and y==0:tau=1-lh*la*rho
    elif x==1 and y==0:tau=1+la*rho
    elif x==0 and y==1:tau=1+lh*rho
    elif x==1 and y==1:tau=1-rho
    raw.append(max(0,tau)*ph[x]*pa[y])
  z=sum(raw) or 1;p={'h':0,'d':0,'a':0};i=0
  for x in range(9):
   for y in range(9):p['h' if x>y else 'a' if x<y else 'd']+=raw[i]/z;i+=1
  return norm(p),sum(raw[i*9+i]/z for i in range(9))
 def _recalibrate_league(self, ts):
  L=self._league(); hist=self.history[-120:]
  if len(hist)<30:return
  # Estimate rho on the observed low-score cells using a bounded grid.
  best=(float('-inf'),L.rho)
  for rho in [round(-.20+i*.01,2) for i in range(27)]:
   ll=0.0
   for x in hist:
    lh=max(.2,L.home_goals);la=max(.2,L.away_goals)
    ph=poisson(x['gh'],lh);pa=poisson(x['ga'],la);tau=1
    if x['gh']==0 and x['ga']==0:tau=1-lh*la*rho
    elif x['gh']==1 and x['ga']==0:tau=1+la*rho
    elif x['gh']==0 and x['ga']==1:tau=1+lh*rho
    elif x['gh']==1 and x['ga']==1:tau=1-rho
    ll+=log(max(1e-12,tau*ph*pa))
   if ll>best[0]:best=(ll,rho)
  L.rho=best[1]
  # xi is selected from a conservative recency grid by weighted score likelihood.
  ages=[max(0,(ts-x['ts'])/86400) for x in hist]
  candidates=[.003,.006,.009,.012]; scores=[]
  for xi in candidates:
   score=sum(exp(-xi*age)*log(max(1e-12,poisson(x['gh'],max(.2,L.home_goals))*poisson(x['ga'],max(.2,L.away_goals)))) for x,age in zip(hist,ages))
   scores.append((score,xi))
  L.xi=max(scores)[1]
  L.hfa=max(.05,min(.25,sum(x['gh']-x['ga'] for x in hist)/max(1,len(hist))))
 def predict(self,h,a,ts,market=None,news=None):
  lh,la=self._lambdas(h,a,ts); L=self._league(); p,draw_mass=self._dc(lh,la,L.rho)
  # Context is a bounded probability correction, H2H only 5% of context.
  shift=.035*self._context(h,a,ts);p=norm({'h':p['h']+shift,'d':p['d'],'a':p['a']-shift})
  # Optional structured team news: values are fractional attack/defence absences.
  if news:
   lh*=max(.85,min(1.05,1-float(news.get('home_attack_absence',0))))
   la*=max(.85,min(1.05,1-float(news.get('away_attack_absence',0))))
   p,_=self._dc(lh,la,L.rho)
  internal=norm(p)
  if market:
   m=norm({k:1/float(market[k]) for k in OUT}) if all(float(market[k])>1 for k in OUT) else norm(market)
   final=norm({k:.40*internal[k]+.60*m[k] for k in OUT}); weight_market=.60
  else: final=internal;weight_market=0.0
  return {'h':final['h'],'d':final['d'],'a':final['a'],'internal':internal,'lh':lh,'la':la,'market_weight':weight_market}
 def update(self,h,a,gh,ga,ts):
  h=normalize_team(h);a=normalize_team(a);ht,at=self._team(h),self._team(a);L=self._league();
  self._decay(ht,ts);self._decay(at,ts)
  predh,preda=self._lambdas(h,a,ts); gd=abs(gh-ga); k=0.055*(1.4 if ht.played<8 or at.played<8 else 1.0)*(1+0.35*log(1+gd))
  # attack and defence updates are regularized toward 1
  ht.attack=max(.55,min(1.65,ht.attack+k*((gh/max(.2,predh))-1))); at.defence=max(.55,min(1.65,at.defence+k*((gh/max(.2,predh))-1)))
  at.attack=max(.55,min(1.65,at.attack+k*((ga/max(.2,preda))-1))); ht.defence=max(.55,min(1.65,ht.defence+k*((ga/max(.2,preda))-1)))
  ht.home=max(-.25,min(.25,ht.home+.02*((gh-ga)-L.hfa)));at.away=max(-.25,min(.25,at.away+.02*((ga-gh))))
  for t,gf,ga_,venue in ((ht,gh,ga,'home'),(at,ga,gh,'away')):
   pts=3 if gf>ga_ else 1 if gf==ga_ else 0; t.played+=1;t.points+=pts
   opp=max(.7,min(1.3,(self._team(a if t is ht else h).attack+self._team(a if t is ht else h).defence)/2))
   t.recent.append({'signal':max(-1,min(1,(pts/3-.5)*1.5+(gf-ga_)/3))*opp,'weight':1+0.35*(5-len(t.recent))})
  L.home_goals=(L.home_goals*L.played+gh)/(L.played+1);L.away_goals=(L.away_goals*L.played+ga)/(L.played+1);L.hfa=(L.hfa*L.played+(gh-ga)/3)/(L.played+1);L.played+=1
  self.history.append({'h':h,'a':a,'gh':gh,'ga':ga,'ts':ts})
  if L.played%30==0:self._recalibrate_league(ts)
