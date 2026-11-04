"""隔离官方/授权受注清单与普通足球赛程。未经授权的数据绝不自动标记官方。"""
import csv, json, re, sqlite3
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from core import DB,DATA_DIR,now,normal_date,log,db_session
from sources import request_json, kickoff_cst, proxy_xg

REQUIRED=['jc_no','date','kickoff','league','home','away']


def initialize():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    with db_session(DB) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS official_fixture (
          jc_no TEXT NOT NULL, date TEXT NOT NULL, kickoff TEXT NOT NULL,
          league TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL,
          info_source TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
          review_state TEXT NOT NULL DEFAULT '待核对', feed_synced_at TEXT NOT NULL,
          home_xg REAL, away_xg REAL, model_source TEXT NOT NULL DEFAULT '',
          match_info TEXT NOT NULL DEFAULT '', history_home INTEGER NOT NULL DEFAULT 0,
          history_away INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(date,jc_no))''')


def parse_fixture(d,source,source_url='',review_state='待核对'):
    if not isinstance(d,dict):raise ValueError('单场格式必须为JSON对象')
    for k in REQUIRED:
        if not str(d.get(k) or '').strip():raise ValueError(f'缺少字段{k}')
    date=normal_date(d['date'])
    j=str(d['jc_no']).strip()
    if len(j)>32 or not re.fullmatch(r'[\w\u4e00-\u9fff-]+',j):raise ValueError('竞彩编号格式异常')
    raw=str(d['kickoff']).strip()
    # yyyy-mm-dd hh:mm Beijing local
    try: stamp=datetime.strptime(raw,'%Y-%m-%d %H:%M')
    except ValueError:raise ValueError('kickoff须为北京时间 YYYY-MM-DD HH:MM')
    if abs((stamp.date()-datetime.strptime(date,'%Y-%m-%d').date()).days)>1:raise ValueError('开赛日期和竞彩日期相差超过1天')
    result={'jc_no':j,'date':date,'kickoff':raw,'league':str(d['league']).strip(),
      'home':str(d['home']).strip(),'away':str(d['away']).strip(),
      'info_source':source,'source_url':source_url,'review_state':review_state}
    if result['home']==result['away']:raise ValueError('主客队不能相同')
    return result


def store(rows,source,source_url='',review_state='待核对'):
    initialize()
    clean=[parse_fixture(r,source,source_url,review_state) for r in rows]
    ids=[(x['date'],x['jc_no']) for x in clean]
    if len(ids)!=len(set(ids)):raise ValueError('同一竞彩日期存在重复编号')
    if not clean:raise ValueError('没有可用的场次')
    with db_session(DB) as db:
        for r in clean:
            db.execute('''INSERT INTO official_fixture(jc_no,date,kickoff,league,home,away,info_source,source_url,review_state,feed_synced_at)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date,jc_no) DO UPDATE SET
            kickoff=excluded.kickoff,league=excluded.league,home=excluded.home,away=excluded.away,
            info_source=excluded.info_source,source_url=excluded.source_url,review_state=excluded.review_state,
            feed_synced_at=excluded.feed_synced_at,
            home_xg=CASE WHEN home<>excluded.home OR away<>excluded.away OR kickoff<>excluded.kickoff THEN NULL ELSE home_xg END,
            away_xg=CASE WHEN home<>excluded.home OR away<>excluded.away OR kickoff<>excluded.kickoff THEN NULL ELSE away_xg END''',
            (r['jc_no'],r['date'],r['kickoff'],r['league'],r['home'],r['away'],r['info_source'],r['source_url'],r['review_state'],now().isoformat()))
    log(f'受注清单导入: {len(clean)}场 来源={source} 审核={review_state}')
    return len(clean)


def import_official_csv(filename):
    with open(filename,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not set(REQUIRED).issubset(reader.fieldnames or []):raise ValueError('CSV应包含 '+','.join(REQUIRED))
        rows=list(reader)
    # 用户导入的CSV不是官方认证，即使用户填写官方名称也待核对
    return store(rows,'用户导入的待核对清单',review_state='待核对')


def import_authorized_feed(url,token,day):
    u=urlparse(url)
    if u.scheme!='https' or not u.netloc or u.username or u.password:raise ValueError('授权JSON源必须为HTTPS地址')
    headers={'Authorization':'Bearer '+token} if token else {}
    d=request_json(url,headers,timeout=25)
    rows=d if isinstance(d,list) else d.get('fixtures') if isinstance(d,dict) else None
    if not isinstance(rows,list):raise ValueError('JSON须为数组或包含fixtures数组')
    if isinstance(d,dict) and d.get('error'):raise ValueError('供应商返回错误')
    filtered=[x for x in rows if isinstance(x,dict) and str(x.get('date',''))==day]
    if not filtered:raise ValueError('接口未返回所选日期的受注清单；现有历史数据未覆盖')
    # 授权供应商的有效数据不等于国家体彩中心直接验证；仍标记待核对
    return store(filtered,'用户配置的授权竞彩数据接口',url,'供应商来源·待官方核对')


def load(day):
    initialize()
    with db_session(DB) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute('SELECT * FROM official_fixture WHERE date=? ORDER BY kickoff,jc_no',(normal_date(day),))]


def record_confirmation(day,jc_no,confirmed,source_url=''):
    """人工确认并记录日期/编号。操作仅为用户对照记录，不代表官方认证。"""
    initialize()
    with db_session(DB) as db:
        n=db.execute('UPDATE official_fixture SET review_state=?,source_url=? WHERE date=? AND jc_no=?',
          ('用户已核对官方页面' if confirmed else '待核对',source_url,normal_date(day),jc_no)).rowcount
    if not n:raise ValueError('未找到待确认场次')
    log(f'用户人工核对 {day} {jc_no} 结果={confirmed}')


def normalized_team(t):
    # Intentional conservative matching: no guessing Chinese->English team names.
    return re.sub('[^a-z0-9]','',str(t).lower().replace('football club','').replace(' fc','').replace(' cf',''))


def alias_map(filename=None):
    filename=Path(filename or DATA_DIR/'team_aliases.csv')
    mapping={}
    if filename.exists():
        with filename.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                a=normalized_team(r.get('official',''));b=normalized_team(r.get('provider',''))
                if a and b:mapping[a]=b
    return mapping


def enrich_from_football_data(day,token,competitions=('PL','PD','BL1','SA'),aliases=None):
    """从football-data历史中严格匹配双方及开球时刻，再用赛前历史进球建模。"""
    if not token:raise ValueError('请在数据源设置中填写football-data.org Token')
    from datetime import timedelta
    from urllib.parse import urlencode
    from sources import request_json
    rows=load(day)
    if not rows:raise ValueError('请先导入指定日期的竞彩受注清单，再补充历史数据')
    alias=aliases if aliases is not None else alias_map()
    earliest=datetime.strptime(day,'%Y-%m-%d').date()-timedelta(days=180)
    latest=datetime.strptime(day,'%Y-%m-%d').date()+timedelta(days=2)
    matches=[];warnings=[]
    for code in competitions:
        try:
            url='https://api.football-data.org/v4/competitions/'+code+'/matches?'+urlencode({'dateFrom':earliest.isoformat(),'dateTo':latest.isoformat()})
            payload=request_json(url,{'X-Auth-Token':token},timeout=25)
            matches.extend(payload.get('matches') or [])
        except Exception as exc:warnings.append(f'{code}: {type(exc).__name__}: {exc}')
    if not matches:raise RuntimeError('未获取到历史赛事。'+'；'.join(warnings))
    changed=0;skipped=[]
    for r in rows:
        kickoff=datetime.strptime(r['kickoff'],'%Y-%m-%d %H:%M').replace(tzinfo=__import__('core').CST)
        hn=normalized_team(r['home']);an=normalized_team(r['away'])
        hn=alias.get(hn,hn);an=alias.get(an,an)
        contenders=[]
        for m in matches:
            dt=kickoff_cst(m.get('utcDate'))
            if dt is None or abs((dt-kickoff).total_seconds())>4*3600:continue
            home=m.get('homeTeam') or {};away=m.get('awayTeam') or {}
            if normalized_team(home.get('name'))==hn and normalized_team(away.get('name'))==an:
                contenders.append(m)
        if len(contenders)!=1:
            skipped.append(f'{r["jc_no"]} 球队名或开赛时间未唯一匹配（{len(contenders)}条）');continue
        match=contenders[0];h=match['homeTeam'];a=match['awayTeam']
        est=proxy_xg(matches,h.get('id'),a.get('id'),kickoff,min_team_games=5)
        if not est:
            skipped.append(f'{r["jc_no"]} 赛前已完赛样本不足');continue
        # Count exact history games for audit (proxy may use home/away fallback)
        hcount=acount=0
        for x in matches:
            dt=kickoff_cst(x.get('utcDate'))
            if x.get('status')!='FINISHED' or dt is None or dt>=kickoff:continue
            scores=(x.get('score') or {}).get('fullTime') or {}
            if not isinstance(scores.get('home'),int) or not isinstance(scores.get('away'),int):continue
            if h['id'] in ((x.get('homeTeam') or {}).get('id'),(x.get('awayTeam') or {}).get('id')):hcount+=1
            if a['id'] in ((x.get('homeTeam') or {}).get('id'),(x.get('awayTeam') or {}).get('id')):acount+=1
        with db_session(DB) as db:
            db.execute('''UPDATE official_fixture SET home_xg=?,away_xg=?,model_source=?,match_info=?,history_home=?,history_away=?
                          WHERE date=? AND jc_no=?''',
                       (est[0],est[1],est[2],f'football-data match={match.get("id")}',hcount,acount,r['date'],r['jc_no']))
        changed+=1
    log(f'体彩清单历史分析完成 day={day} 完成={changed} 跳过={len(skipped)}')
    return changed,skipped+warnings
