"""New verified-fixture research GUI panel; keeps old third-party match pane separate."""
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import threading,webbrowser,os
import core,official,refresh

class OfficialPanel(ttk.Frame):
    def __init__(self,master,day,status):
        super().__init__(master)
        self.day,self.status=day,status
        self.build();self.load()

    def build(self):
        tk.Label(self,text='竞彩足球受注清单｜来源核对与赛前概率研究',bg='#eef3f8',fg='#164563',font=('Microsoft YaHei UI',13,'bold'),anchor='w').pack(fill='x',pady=(8,6))
        tk.Label(self,text='须有竞彩编号；手动导入和授权供应商数据均不自动视为官方认证。选择场次后可记录人工核对。',fg='#87531e',anchor='w').pack(fill='x',pady=(0,8))
        bar=ttk.Frame(self);bar.pack(fill='x',pady=4)
        for name,cb in [('导入竞彩清单CSV',self.import_csv),('同步授权受注接口',self.sync_feed),('匹配历史并建模',self.enrich),('核对官方网站',lambda:webbrowser.open('https://www.sporttery.cn/')),('标记已人工核对',self.confirm),('刷新场次',self.load)]:
            ttk.Button(bar,text=name,command=cb).pack(side='left',padx=3)
        columns=[('jc','竞彩编号',95),('league','联赛',120),('time','北京时间',130),('home','主队',145),('away','客队',145),('state','受注核对',145),('prob','主胜/平/客胜',210),('samples','赛前样本',110)]
        wrapper=ttk.Frame(self);wrapper.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(wrapper,show='headings',columns=[x[0] for x in columns],height=11)
        for key,label,width in columns:self.tree.heading(key,text=label);self.tree.column(key,width=width,anchor='center',minwidth=70)
        scrollbar=ttk.Scrollbar(wrapper,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left',expand=True,fill='both');scrollbar.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.detail)
        self.info=tk.Text(self,height=12,wrap='word',font=('Microsoft YaHei UI',10),bg='white',fg='#18334a',padx=12,pady=10)
        self.info.pack(fill='both',expand=True,pady=8);self.info.config(state='disabled')

    def set_info(self,text):
        self.info.config(state='normal');self.info.delete('1.0','end');self.info.insert('1.0',text);self.info.config(state='disabled')

    def load(self):
        try:items=official.load(self.day.get())
        except Exception as exc:messagebox.showerror('读取失败',str(exc));return
        self.tree.delete(*self.tree.get_children());self.mapping={}
        for r in items:
            pred=self.pred(r)
            if pred:
                value=' / '.join(f'{v:.1%}' for v in pred['wdl'])
            else:value='样本不足'
            iid=self.tree.insert('','end',values=(r['jc_no'],r['league'],r['kickoff'],r['home'],r['away'],r['review_state'],value,f'{r["history_home"]}/{r["history_away"]}'))
            self.mapping[iid]=r
        self.status.set(f'竞彩受注清单：{self.day.get()} 共{len(items)}场；竞彩清单来源均需核对，第三方普通赛事单独显示。')
        self.set_info('先通过授权接口或合法来源CSV导入带竞彩编号的受注场次。\n然后配置football-data.org Token，点击“匹配历史并建模”。\n未匹配或赛前样本不足的场次不生成预测。\n软件不提供直接购彩或中奖保证。')

    def pred(self,row):
        if row['home_xg'] is None or row['away_xg'] is None:return None
        return core.predict(row['home_xg'],row['away_xg'])

    def detail(self,_=None):
        s=self.tree.selection()
        if not s:return
        r=self.mapping[s[0]];p=self.pred(r)
        out=[f'{r["jc_no"]} | {r["league"]} | {r["home"]} vs {r["away"]}',
             '比赛时间（北京时间）：'+r['kickoff'], '清单来源：'+r['info_source'],
             '人工核对状态：'+r['review_state'], '历史来源：'+(r['model_source'] or '未分析'),
             '历史数据样本量：主队'+str(r['history_home'])+'场，客队'+str(r['history_away'])+'场',
             '来源链接：'+r['source_url']]
        if p:
            out+=['','胜平负：'+'  '.join(f'{name} {x:.1%}' for name,x in zip(['主胜','平局','客胜'],p['wdl'])),
                  '概率前5比分：'+'、'.join(f'{x["score"]}({x["p"]:.1%})' for x in p['scores']),
                  '总进球分布：'+'  '.join(f'{i if i<7 else "7+"}球 {v:.1%}' for i,v in enumerate(p['totals'])),
                  '预期进球代理值：主'+str(r['home_xg'])+' 客'+str(r['away_xg'])]
        else:out+=['','该场没有可用的赛前进球估计值，暂不提供概率。']
        out+=['','提示：这是基于进失球均值的独立泊松模型，不含球员伤停、首发及盘口赔率。模型概率≠中奖率；竞彩购买资格、固定奖金及停售以官方为准。']
        self.set_info('\n'.join(out))

    def import_csv(self):
        path=filedialog.askopenfilename(title='合法来源的竞彩受注清单',filetypes=[('CSV','*.csv')])
        if not path:return
        try:n=official.import_official_csv(path);self.load();messagebox.showinfo('成功',f'导入 {n} 场。当前均为“待核对”，请对照官方页面确认。')
        except Exception as exc:messagebox.showerror('导入失败',str(exc))

    def _run_task(self,label,func):
        self.status.set(label+'，请勿重复点击。')
        def work():
            try:r=func();self.after(0,lambda:self._finish(label,r,None))
            except Exception as exc:
                core.log(label+' '+repr(exc));msg=str(exc);self.after(0,lambda:self._finish(label,None,msg))
        threading.Thread(target=work,daemon=True).start()

    def _finish(self,label,result,error):
        self.load()
        if error:messagebox.showerror(label+'失败',error)
        else:
            n,w=result
            messagebox.showinfo(label+'完成',f'处理 {n} 场。'+ ('\n提醒：\n'+'\n'.join(w[:8]) if w else ''))

    def sync_feed(self):
        self._run_task('同步授权受注接口',lambda:(refresh.sync_official(self.day.get()),[]))

    def enrich(self):
        self._run_task('赛前历史建模',lambda:refresh.enrich_official(self.day.get()))

    def confirm(self):
        s=self.tree.selection()
        if not s:messagebox.showinfo('提示','请先选中一场比赛');return
        row=self.mapping[s[0]]
        if not messagebox.askyesno('核对确认',f'请先亲自对照中国竞彩网的竞彩编号、双方及北京时间：\n{row["jc_no"]} {row["home"]} vs {row["away"]}\n\n是否已核对一致？'):
            return
        official.record_confirmation(row['date'],row['jc_no'],True,'https://www.sporttery.cn/')
        self.load()
