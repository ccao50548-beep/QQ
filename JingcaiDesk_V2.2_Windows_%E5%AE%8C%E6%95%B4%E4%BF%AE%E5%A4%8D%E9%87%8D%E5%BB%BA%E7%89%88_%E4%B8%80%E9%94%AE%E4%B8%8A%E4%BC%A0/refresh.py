"""批处理/每日11点作业，供GUI与Windows任务计划程序共用。"""
import json,os,sys
from pathlib import Path
import core,sources,official
CONFIG=core.DATA_DIR/'config.json'

def read_config():
    try:return json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def save_config(c):
    core.DATA_DIR.mkdir(parents=True,exist_ok=True)
    CONFIG.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')

def sync_day(day=None):
    core.init_db();day=day or core.now().date().isoformat()
    c=read_config();mode=c.get('provider','TheSportsDB（免费赛程）')
    if mode=='football-data.org（需Token）':
        token=os.environ.get('FOOTBALL_DATA_TOKEN','').strip() or c.get('football_token','').strip()
        rows,warnings=sources.football_data_day(day,token,tuple(x.strip() for x in c.get('competitions','PL,PD,BL1,SA').split(',') if x.strip()))
    elif mode=='授权竞彩JSON接口':
        url=c.get('feed_url','').strip()
        if not url:raise ValueError('请先配置授权JSON数据地址')
        n=core.import_url(url,os.environ.get('JINGCAI_FEED_TOKEN',''))
        core.set_meta('last_online_day',day)
        core.log('联网同步完成：授权JSON '+str(n))
        return n,[]
    else:rows,warnings=sources.thesportsdb_day(day)
    if not rows:
        core.log(f'网络请求成功但{day}无可用比赛；数据源={mode}。请勿视为中国体彩无可售场次。')
        core.set_meta('last_online_day',day)
        core.set_meta('last_online_status','空结果（非体彩官方）')
        return 0,warnings
    n=core.save_matches(rows,mode+' / 非官方受注清单')
    core.set_meta('last_online_day',day)
    core.set_meta('last_online_status','同步成功')
    for w in warnings:core.log('局部获取失败：'+w)
    return n,warnings

def headless():
    try:
        core.init_db();day=core.now().date().isoformat()
        c=read_config()
        n=0; w=[]
        if c.get('feed_url','').strip():
            try:
                n=sync_official(day)
                if c.get('football_token','').strip() or os.environ.get('FOOTBALL_DATA_TOKEN','').strip():
                    _,more=enrich_official(day);w+=more
            except Exception as e:
                core.log('竞彩受注同步或建模失败: '+repr(e));w.append(str(e))
                # Never silently fall back to a generic schedule as "official".
        else:
            n,w=sync_day(day)
        reports=core.DATA_DIR/'reports';reports.mkdir(exist_ok=True)
        core.export_report(reports/f'竞彩足球研究_{day}.html',day)
        core.log(f'11点作业完成，场次 {n}，部分错误 {len(w)}')
        return 1 if w and c.get('feed_url','').strip() and n==0 else 0
    except Exception as e:
        core.log(f'11点作业失败：{type(e).__name__}: {e}')
        core.set_meta('last_online_status','失败：'+str(e)[:250]);return 1

if __name__=='__main__':sys.exit(headless())


def sync_official(day=None):
    day=day or core.now().date().isoformat()
    c=read_config()
    url=c.get('feed_url','').strip()
    if not url:raise ValueError('请在“数据源设置”填写已获授权的竞彩清单JSON地址')
    token=os.environ.get('JINGCAI_FEED_TOKEN','').strip() or c.get('feed_token','').strip()
    n=official.import_authorized_feed(url,token,day)
    core.log(f'竞彩受注清单自动同步成功 {day} 数量={n}')
    return n

def enrich_official(day=None):
    day=day or core.now().date().isoformat()
    c=read_config()
    token=os.environ.get('FOOTBALL_DATA_TOKEN','').strip() or c.get('football_token','').strip()
    codes=tuple(x.strip() for x in c.get('competitions','PL,PD,BL1,SA').split(',') if x.strip())
    return official.enrich_from_football_data(day,token,codes)
