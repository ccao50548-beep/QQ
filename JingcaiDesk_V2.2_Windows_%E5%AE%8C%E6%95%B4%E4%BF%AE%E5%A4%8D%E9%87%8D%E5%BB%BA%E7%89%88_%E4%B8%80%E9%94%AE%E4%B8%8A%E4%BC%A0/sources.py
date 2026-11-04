"""网络赛程源：第三方赛程 != 中国体彩竞彩足球受注名单。"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json, math, os
from collections import defaultdict
from core import CST, normal_date, now

HEADERS={'User-Agent':'JingcaiDesk/2.0 (personal research)','Accept':'application/json'}

def request_json(url, headers=None, timeout=25):
    h=dict(HEADERS);h.update(headers or {})
    req=Request(url,headers=h)
    with urlopen(req,timeout=timeout) as r:
        payload=r.read(10_000_001)
        if len(payload)>10_000_000:raise ValueError('服务端响应超过10MB')
    return json.loads(payload.decode('utf-8-sig'))

def kickoff_cst(utc_text):
    if not utc_text:return None
    try:
        s=utc_text.replace('Z','+00:00')
        d=datetime.fromisoformat(s)
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(CST)
    except (TypeError,ValueError):return None

def proxy_xg(history, home, away, before, min_team_games=5):
    """用赛前已完赛比赛的进失球估算泊松均值，非真实xG；不泄漏未来结果。"""
    records=[]
    for r in history:
        if r.get('status')!='FINISHED':continue
        t=r.get('utcDate')
        dt=kickoff_cst(t)
        if dt is None or dt >= before:continue
        full=(r.get('score') or {}).get('fullTime') or {}
        hg,ag=full.get('home'),full.get('away')
        if not isinstance(hg,int) or not isinstance(ag,int):continue
        hn=((r.get('homeTeam') or {}).get('id'))
        an=((r.get('awayTeam') or {}).get('id'))
        records.append((dt,hn,an,hg,ag))
    records.sort(reverse=True)
    home_all=[(hg,ag,hn==home) for dt,hn,an,hg,ag in records if hn==home or an==home][:12]
    away_all=[(ag,hg,an==away) for dt,hn,an,hg,ag in records if hn==away or an==away][:12]
    if len(home_all)<min_team_games or len(away_all)<min_team_games:return None
    def team_form(tid, prefer_home):
        values=[]
        for dt,hn,an,hg,ag in records:
            if hn==tid:values.append((hg,ag,True))
            elif an==tid:values.append((ag,hg,False))
            if len(values)>=12:break
        preferred=[(f,a) for f,a,is_home in values if is_home==prefer_home]
        # fallback to overall form if venue sample inadequate
        if len(preferred)<3:preferred=[(f,a) for f,a,_ in values]
        return sum(f for f,_ in preferred)/len(preferred),sum(a for _,a in preferred)/len(preferred)
    home_for,home_against=team_form(home,True)
    away_for,away_against=team_form(away,False)
    # conservative blend to league mean; cap to avoid spuriously extreme probabilities
    lam_h=min(3.7,max(.35,.55*(home_for+away_against)/2+.45*1.40))
    lam_a=min(3.7,max(.35,.55*(away_for+home_against)/2+.45*1.15))
    return (round(lam_h,3),round(lam_a,3),f'历史进失球代理模型：主队{len(home_all)}场/客队{len(away_all)}场；非真实xG')

def football_data_day(day,token,competitions=('PL','PD','BL1','SA')):
    """使用football-data.org v4每联赛一次请求，取历史+今日日程；受到订阅等级限制。"""
    if not token:raise ValueError('football-data.org需要API Token。请在设置中填写或配置环境变量 FOOTBALL_DATA_TOKEN。')
    target=datetime.strptime(normal_date(day),'%Y-%m-%d').date()
    date_from=(target-timedelta(days=135)).isoformat()
    # Beijing day may cover parts of adjacent UTC date
    date_to=(target+timedelta(days=1)).isoformat()
    rows=[];errors=[]
    for code in competitions:
        try:
            url=f'https://api.football-data.org/v4/competitions/{code}/matches?'+urlencode({'dateFrom':date_from,'dateTo':date_to})
            d=request_json(url,{'X-Auth-Token':token})
            history=d.get('matches',[])
            for m in history:
                kickoff=kickoff_cst(m.get('utcDate'))
                if kickoff is None or kickoff.date()!=target or m.get('status') in ('FINISHED','CANCELLED','POSTPONED'):continue
                h=m.get('homeTeam') or {};a=m.get('awayTeam') or {}
                if not h.get('name') or not a.get('name'):continue
                xg=proxy_xg(history,h.get('id'),a.get('id'),kickoff)
                rows.append({'match_id':'FD-'+str(m['id']),'date':target.isoformat(),'kickoff':kickoff.strftime('%Y-%m-%d %H:%M'),
                  'league':(d.get('competition') or {}).get('name',code), 'home':h['name'],'away':a['name'],
                  'home_xg':xg[0] if xg else '', 'away_xg':xg[1] if xg else '',
                  'xg_source':xg[2] if xg else '历史比赛样本不足（不生成概率）',
                  'source':f'football-data.org v4 / {code}；普通足球赛程，未核验体彩受注'})
        except Exception as ex:errors.append(f'{code}: {type(ex).__name__}: {ex}')
    if not rows and errors:raise RuntimeError('未获取可用场次。'+'；'.join(errors))
    return rows,errors

def thesportsdb_day(day):
    target=normal_date(day)
    url='https://www.thesportsdb.com/api/v1/json/123/eventsday.php?'+urlencode({'d':target,'s':'Soccer'})
    payload=request_json(url)
    out=[]
    for event in payload.get('events') or []:
        if event.get('strSport') not in (None,'Soccer'):continue
        dt=kickoff_cst(event.get('strTimestamp'))
        # Some feeds expose only local date, avoid silently treating as CST
        if dt is None:continue
        if dt.date().isoformat()!=target:continue
        if not event.get('strHomeTeam') or not event.get('strAwayTeam'):continue
        out.append({'match_id':'TSDB-'+str(event.get('idEvent')),'date':target,'kickoff':dt.strftime('%Y-%m-%d %H:%M'),
           'league':event.get('strLeague') or '未标明', 'home':event['strHomeTeam'],'away':event['strAwayTeam'],
           'home_xg':'','away_xg':'','xg_source':'无可信历史参数，不提供预测',
           'source':'TheSportsDB公开足球赛程；普通比赛，未核验体彩受注'})
    return out,[]
