"""竞彩足球概率研究。仅分析常规时间90分钟含补时，不包含加时点球。"""
import csv, json, math, os, sqlite3
from pathlib import Path
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

CST=timezone(timedelta(hours=8))
DATA_DIR=Path(os.environ.get('APPDATA',str(Path.home()))) / 'JingcaiDesk'
DB=DATA_DIR/'matches.sqlite3'
LOG=DATA_DIR/'refresh.log'
@contextmanager
def db_session(db_path):
    """Commit/rollback AND close SQLite connection (important on Windows)."""
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            yield connection

FIELDS=['match_id','date','kickoff','league','home','away','home_xg','away_xg','xg_source','source']

def now(): return datetime.now(CST)
def log(msg):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    with LOG.open('a',encoding='utf-8') as f:f.write(f'[{now().isoformat(timespec="seconds")}] {msg}\n')

def init_db():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    with db_session(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS matches(match_id TEXT PRIMARY KEY,date TEXT NOT NULL,kickoff TEXT,league TEXT,home TEXT NOT NULL,away TEXT NOT NULL,home_xg REAL,away_xg REAL,xg_source TEXT,source TEXT,updated_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')

def set_meta(key,value):
    with db_session(DB) as db:db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
def get_meta(key):
    with db_session(DB) as db:
        a=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return a[0] if a else None

def normal_date(s):
    s=str(s).strip()
    return datetime.strptime(s,'%Y-%m-%d').date().isoformat()

def parse_xg(v):
    if v is None or str(v).strip()=='':return None
    x=float(v)
    if not (0.05<=x<=6):raise ValueError('预期进球参数须在0.05至6之间')
    return x

def normalize(row):
    r={k:str(row.get(k) or '').strip() for k in FIELDS}
    for k in ('match_id','date','home','away'):
        if not r[k]:raise ValueError('缺少必要字段 '+k)
    r['date']=normal_date(r['date'])
    r['home_xg']=parse_xg(row.get('home_xg'))
    r['away_xg']=parse_xg(row.get('away_xg'))
    if (r['home_xg'] is None)!=(r['away_xg'] is None):
        raise ValueError('预期进球参数必须同时提供主客两方')
    r['xg_source']=r['xg_source'] or '未提供'
    return r

def save_matches(rows, source_label='CSV'):
    init_db();clean=[normalize(r) for r in rows]
    if not clean:raise ValueError('没有找到场次记录')
    with db_session(DB) as db:
        for r in clean:
            db.execute('''INSERT INTO matches(match_id,date,kickoff,league,home,away,home_xg,away_xg,xg_source,source,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET
            date=excluded.date,kickoff=excluded.kickoff,league=excluded.league,home=excluded.home,away=excluded.away,
            home_xg=excluded.home_xg,away_xg=excluded.away_xg,xg_source=excluded.xg_source,source=excluded.source,updated_at=excluded.updated_at''',
            (r['match_id'],r['date'],r['kickoff'],r['league'],r['home'],r['away'],r['home_xg'],r['away_xg'],r['xg_source'],r['source'] or source_label,now().isoformat()))
    set_meta('last_success',now().isoformat());set_meta('last_source',source_label)
    log(f'成功导入 {len(clean)} 场 来源={source_label}')
    return len(clean)

def import_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        rdr=csv.DictReader(f)
        if not set(['match_id','date','home','away']).issubset(rdr.fieldnames or []):raise ValueError('CSV缺少 match_id,date,home,away 必需列')
        return save_matches(list(rdr),str(path))

def import_url(url,api_key=''):
    """仅支持用户有权使用的JSON数据源，格式见README；不存储密钥。"""
    if not url.startswith('https://'):raise ValueError('仅允许 HTTPS JSON 数据接口')
    headers={'User-Agent':'JingcaiDesk/1.0','Accept':'application/json'}
    if api_key:headers['Authorization']='Bearer '+api_key
    req=Request(url,headers=headers)
    with urlopen(req,timeout=25) as response:
        if response.status!=200:raise RuntimeError(f'HTTP {response.status}')
        raw=response.read(5_000_001)
        if len(raw)>5_000_000:raise ValueError('接口返回过大')
    payload=json.loads(raw)
    rows=payload if isinstance(payload,list) else payload.get('matches')
    if not isinstance(rows,list):raise ValueError('JSON应为数组或包含matches数组的对象，不能直接使用未适配的供应商接口')
    return save_matches(rows,url.split('?')[0])

def load_matches(date=None):
    init_db();date=date or now().date().isoformat()
    with db_session(DB) as db:
        db.row_factory=sqlite3.Row
        return [dict(x) for x in db.execute('SELECT * FROM matches WHERE date=? ORDER BY kickoff,match_id',(date,))]

def poisson(k,lam):return math.exp(-lam)*lam**k/math.factorial(k)

def predict(home_xg,away_xg):
    h=parse_xg(home_xg);a=parse_xg(away_xg)
    if h is None or a is None:raise ValueError('缺少双方有效预期进球，不能预测')
    max_goal=18
    hp=[poisson(i,h) for i in range(max_goal+1)]
    ap=[poisson(i,a) for i in range(max_goal+1)]
    outcomes=[0.,0.,0.]
    totals=[0.]*8
    scores=[]
    for i in range(max_goal+1):
        for j in range(max_goal+1):
            p=hp[i]*ap[j]
            outcomes[0 if i>j else 1 if i==j else 2]+=p
            totals[min(7,i+j)]+=p
            scores.append((p,i,j))
    residual=1-sum(outcomes)
    # at 18 goals tail tiny; do not silently normalize materially incomplete distributions
    if residual>1e-5:raise ValueError('模型截断误差过大')
    scores.sort(reverse=True)
    return {'wdl':outcomes,'totals':totals,'scores':[{'score':f'{i}:{j}','p':p} for p,i,j in scores[:5]],'top_total':max(range(8),key=totals.__getitem__),'max_wdl':max(outcomes),'model':'独立泊松模型(非赔率、非胜率保证)'}

def analyze(r):
    if r['home_xg'] is None or r['away_xg'] is None:return None
    p=predict(r['home_xg'],r['away_xg'])
    labels=['主胜','平局','客胜']
    idx=max(range(3),key=lambda i:p['wdl'][i]);p['top_wdl']=labels[idx]
    # research priority is not betting expected value, since payout odds unknown
    p['priority']='优先研究' if p['wdl'][idx]>=0.58 and r.get('xg_source','') not in ('未提供','示例参数') else '普通观察'
    return p

def export_report(path,day=None):
    import html
    day=day or now().date().isoformat()
    rows=load_matches(day)
    parts=[f'<h1>竞彩足球概率研究日报 {html.escape(day)}</h1>',
           '<p>仅供独立研究；第三方足球赛程不等于体彩竞彩足球受注比赛。模型不是竞彩官方数据或投注建议。预测不保证命中。彩票可能亏损。</p>',
           '<p>90分钟含伤停补时；不含加时赛与点球。联网赛程需核对官方受注资格。部分参数来自历史进失球代理模型，而非真实xG。</p>',
           '<table border="1" cellspacing="0" cellpadding="8"><tr><th>场次</th><th>球队</th><th>胜/平/负</th><th>前3比分</th><th>总进球最可能</th><th>状态</th><th>赛程来源</th><th>模型参数来源</th></tr>']
    for r in rows:
        p=analyze(r)
        if p:
            pred=' / '.join(f'{x:.1%}' for x in p['wdl']);score='、'.join(x['score'] for x in p['scores'][:3]);total=f'{p["top_total"] if p["top_total"]<7 else "7+"}球';flag=p['priority']
        else:pred=score=total='—';flag='缺少模型参数'
        parts.append('<tr>'+''.join(f'<td>{html.escape(str(s))}</td>' for s in [r['match_id'],r['home']+' vs '+r['away'],pred,score,total,flag,r['source'],r['xg_source']])+'</tr>')
    parts.append('</table><p>生成时间：'+now().isoformat(timespec='seconds')+'</p>')
    Path(path).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>竞彩研究日报</title><body>'+''.join(parts)+'</body></html>',encoding='utf-8')
    return path
