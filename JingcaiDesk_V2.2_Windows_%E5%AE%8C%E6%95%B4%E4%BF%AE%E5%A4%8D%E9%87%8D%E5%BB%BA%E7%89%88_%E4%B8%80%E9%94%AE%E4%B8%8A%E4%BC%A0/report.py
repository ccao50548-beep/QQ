"""Simple audited local HTML report; no external JS or tracking."""
from html import escape as esc
from pathlib import Path
import core,official

def export(path,day):
    fixtures=official.load(day)
    sections=[f'<h1>竞彩足球受注清单与概率研究｜{esc(day)}</h1>',
       '<p class="warn">独立第三方研究软件，不是中国体育彩票官方产品。只有经用户核对的场次才标示“用户已核对”；来源为供应商或CSV不代表官方核验。没有历史样本不输出概率。</p>',
       '<p>预测仅针对常规时间90分钟及补时，不包含加时、点球。独立泊松模型有误差，不保证命中；赔率、伤停和最新首发未纳入。</p>']
    for r in fixtures:
        sections.append('<section><h2>'+esc(r['jc_no'])+'｜'+esc(r['home'])+' vs '+esc(r['away'])+'</h2>')
        sections.append('<p>联赛：'+esc(r['league'])+'　北京时间：'+esc(r['kickoff'])+'　状态：'+esc(r['review_state'])+'</p>')
        sections.append('<p>来源：'+esc(r['info_source'])+'　模型依据：'+esc(r['model_source'])+'　赛前样本：'+str(r['history_home'])+' / '+str(r['history_away'])+'</p>')
        if r['home_xg'] is None or r['away_xg'] is None:
            sections.append('<p>暂无充分赛前数据：不生成胜平负、比分或总进球预测。</p>')
        else:
            p=core.predict(r['home_xg'],r['away_xg'])
            sections.append('<p><strong>胜平负：</strong>'+'；'.join(f'{lab}{v:.1%}' for lab,v in zip(('主胜','平局','客胜'),p['wdl']))+'</p>')
            sections.append('<p><strong>比分前五：</strong>'+'；'.join(f'{x["score"]}：{x["p"]:.1%}' for x in p['scores'])+'</p>')
            sections.append('<p><strong>总进球：</strong>'+'；'.join(f'{i if i<7 else "7球及以上"}：{v:.1%}' for i,v in enumerate(p['totals']))+'</p>')
        sections.append('</section>')
    sections.append('<p>报告生成时间（北京时间）：'+esc(core.now().isoformat(timespec='seconds'))+'</p>')
    html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>JingcaiDesk 竞彩研究</title><style>body{font:15px/1.7 "Microsoft YaHei",sans-serif;background:#f5f8fb;color:#19334b;max-width:1080px;margin:35px auto;padding:0 24px}section{padding:18px;margin:14px 0;background:white;border:1px solid #dbe6ef;border-radius:8px}.warn{color:#a35c09}h1{color:#183a5c}</style></head><body>'+''.join(sections)+'</body></html>'
    Path(path).write_text(html,encoding='utf-8')
    return len(fixtures)
