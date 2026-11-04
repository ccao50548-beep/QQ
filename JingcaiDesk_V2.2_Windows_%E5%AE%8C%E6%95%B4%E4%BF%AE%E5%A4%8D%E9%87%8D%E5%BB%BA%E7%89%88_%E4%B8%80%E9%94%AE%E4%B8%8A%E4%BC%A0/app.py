"""JingcaiDesk V2.0: 独立第三方足球比赛研究软件，非竞彩官方。"""
import os,sys,threading,subprocess,traceback,webbrowser
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
import core,refresh,official,official_view,report

def silence_console():
    # PyInstaller --windowed on Windows can set stdout/stderr to None
    if sys.stdout is None:sys.stdout=open(os.devnull,'w',encoding='utf-8')
    if sys.stderr is None:sys.stderr=open(os.devnull,'w',encoding='utf-8')
silence_console()

class App(tk.Tk):
    def __init__(self):
        super().__init__();core.init_db()
        self.title('JingcaiDesk V2.2 · 竞彩场次核对与概率研究（非官方）')
        self.geometry('1240x800');self.minsize(980,640)
        self.configure(bg='#eef3f8')
        s=ttk.Style();s.theme_use('clam');s.configure('Treeview',rowheight=30,font=('Microsoft YaHei UI',10));s.configure('Treeview.Heading',font=('Microsoft YaHei UI',10,'bold'))
        s.configure('TButton',font=('Microsoft YaHei UI',10),padding=6)
        self.day=tk.StringVar(value=core.now().date().isoformat())
        self.status=tk.StringVar(value='准备就绪')
        self.build();self.load()
    def build(self):
        head=tk.Frame(self,bg='#14314c',height=95);head.pack(fill='x');head.pack_propagate(False)
        tk.Label(head,text='JingcaiDesk  V2.2  |  竞彩受注核对与足球数据研究',bg='#14314c',fg='white',font=('Microsoft YaHei UI',19,'bold')).pack(anchor='w',padx=20,pady=(12,0))
        tk.Label(head,text='竞彩编号核对 · 历史进失球模型 · 比分及总进球概率 · 北京时间11点刷新   |   独立第三方软件，非中国体育彩票官方应用',bg='#14314c',fg='#c9d9e7',font=('Microsoft YaHei UI',10)).pack(anchor='w',padx=20)
        bar=ttk.Frame(self);bar.pack(fill='x',padx=12,pady=12)
        ttk.Label(bar,text='北京时间日期').pack(side='left')
        ttk.Entry(bar,width=13,textvariable=self.day).pack(side='left',padx=(5,10))
        actions=[('查看日期',self.load),('联网搜索当日比赛',self.refresh_now),('数据源设置',self.settings),('导入体彩场次CSV',self.import_csv),('导出竞彩研究报告',self.export),('每天11点自动刷新',self.schedule)]
        for name,cb in actions:ttk.Button(bar,text=name,command=cb).pack(side='left',padx=2)
        self.state=tk.Label(self,textvariable=self.status,anchor='w',bg='#d9e9f5',fg='#173850',padx=14,pady=9);self.state.pack(fill='x',padx=13)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True,padx=13,pady=10)
        official_frame=ttk.Frame(tabs);other_frame=ttk.Frame(tabs)
        tabs.add(official_frame,text='竞彩足球受注场次（待核对）')
        tabs.add(other_frame,text='第三方足球赛程（非竞彩清单）')
        self.official_panel=official_view.OfficialPanel(official_frame,self.day,self.status)
        self.official_panel.pack(fill='both',expand=True,padx=8,pady=6)
        panel=ttk.Panedwindow(other_frame,orient='vertical');panel.pack(fill='both',expand=True,padx=3,pady=4)
        upper=ttk.Frame(panel);panel.add(upper,weight=4)
        cols=[('id','来源ID',115),('time','北京时间',125),('league','赛事',140),('home','主队',150),('away','客队',150),('wdl','概率较高方向',115),('top','最可能比分',105),('goal','总进球众数',105),('level','分析状态',130)]
        self.tree=ttk.Treeview(upper,columns=[c[0] for c in cols],show='headings',selectmode='browse')
        for key,label,width in cols:self.tree.heading(key,text=label);self.tree.column(key,width=width,minwidth=80,anchor='center')
        sy=ttk.Scrollbar(upper,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side='left',expand=True,fill='both');sy.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.show_detail)
        lower=ttk.Frame(panel);panel.add(lower,weight=3)
        self.info=tk.Text(lower,wrap='word',font=('Microsoft YaHei UI',10),bg='white',fg='#16344e',padx=18,pady=12)
        self.info.pack(fill='both',expand=True);self.info.config(state='disabled')
        foot=ttk.Frame(self);foot.pack(fill='x',padx=13,pady=(0,10))
        ttk.Button(foot,text='查看更新日志',command=self.logs).pack(side='left')
        ttk.Button(foot,text='打开数据目录',command=self.open_data).pack(side='left',padx=8)
        ttk.Button(foot,text='中国竞彩网（核对受注场次）',command=lambda:webbrowser.open('https://www.sporttery.cn/')).pack(side='left')
        ttk.Label(foot,text='概率仅供研究；未知官方竞彩资格的比赛不会标为可购。购彩有风险，未成年人禁止。').pack(side='right')
    def text(self,s):
        self.info.config(state='normal');self.info.delete('1.0','end');self.info.insert('1.0',s);self.info.config(state='disabled')
    def load(self):
        try:rows=core.load_matches(self.day.get())
        except Exception as e:messagebox.showerror('日期错误',str(e));return
        self.rows={};self.tree.delete(*self.tree.get_children())
        scored=[]
        for r in rows:
            try:p=core.analyze(r)
            except Exception as e:core.log('预测失败 '+r['match_id']+': '+str(e));p=None
            scored.append((r,p))
        scored.sort(key=lambda x:(x[1] is None,-x[1]['max_wdl'] if x[1] else 0,x[0]['kickoff']))
        for r,p in scored:
            top=p['top_wdl']+f' {p["max_wdl"]:.1%}' if p else '参数不足'
            score=p['scores'][0]['score'] if p else '—'
            total=(str(p['top_total']) if p['top_total']<7 else '7+')+'球' if p else '—'
            note=p['priority'] if p else '数据不足'
            iid=self.tree.insert('','end',values=(r['match_id'],r['kickoff'],r['league'],r['home'],r['away'],top,score,total,note))
            self.rows[iid]=(r,p)
        last=core.get_meta('last_success') or '暂无'
        mode=refresh.read_config().get('provider','TheSportsDB（免费赛程）')
        source_age=' ｜ 注意：不是中国体彩官方竞彩受注清单' if any('未核验体彩' in r['source'] or '非官方受注' in r['source'] for r in rows) else ''
        self.status.set(f'{self.day.get()}｜{len(rows)}场｜数据源：{mode}｜最近导入：{last}{source_age}')
        if hasattr(self,'official_panel'):self.official_panel.load()
        self.text('操作说明：\n\n① 点击「联网搜索当日比赛」，联网取得足球赛程。默认免费接口可能只提供部分比赛且没有模型参数。\n\n② 配置 football-data.org 令牌后，可查询支持联赛的赛程与赛前历史进失球，符合最低样本量时才计算概率。\n\n③ 第三方搜索的足球比赛不代表中国体育彩票允许投注。以中国竞彩网为准，必要时导入来自合法渠道的官方受注清单。\n\n④ 选择表格内比赛查看胜平负、比分、总进球和模型局限。\n\n⑤ 不存在保赚场次；没有固定奖金信息时，不作“值得买”结论。')
    def show_detail(self,_=None):
        selection=self.tree.selection()
        if not selection:return
        r,p=self.rows[selection[0]]
        parts=[f'【{r["match_id"]}】{r["home"]} vs {r["away"]}',f'联赛：{r["league"]}  开赛：{r["kickoff"]}（北京时间）',f'赛程来源：{r["source"]}',f'模型参数来源：{r["xg_source"]}',f'本地记录更新时间：{r["updated_at"]}']
        if p:
            parts+=['',f'赛前建模进球均值：主队 {r["home_xg"]:.2f} / 客队 {r["away_xg"]:.2f}', '【胜平负】  '+ '     '.join(f'{s} {v:.1%}' for s,v in zip(('主胜','平','客胜'),p['wdl'])),
               '【比分概率前5】  '+'    '.join(f'{x["score"]} {x["p"]:.1%}' for x in p['scores']),
               '【总进球0—7+】  '+'    '.join(f'{i if i<7 else "7+"}球 {v:.1%}' for i,v in enumerate(p['totals'])),
               '', '研究标签：'+p['priority'],
               '模型风险：独立泊松近似；历史进失球代理值不是官方xG；忽略阵容、伤停、赔率、红牌等因素。']
        else:parts+=['','缺少充分、可验证的赛前进球均值，软件不会生成虚构的比分及概率。']
        parts+=['','【购买资格和风险】第三方赛程≠体育彩票竞彩足球受注赛程。投注前务必在中国竞彩网核对编号、玩法、销售截止时间和固定奖金；本软件不处理投注。']
        self.text('\n'.join(parts))
    def refresh_now(self):
        try:core.normal_date(self.day.get())
        except Exception as e:messagebox.showerror('日期错误',str(e));return
        self.status.set('正在联网搜索……免费源可能限流；软件界面可继续操作。')
        day=self.day.get()
        def work():
            try:
                n,w=refresh.sync_day(day)
                self.after(0,lambda:self.refresh_done(n,w,None))
            except Exception as e:
                core.log('联网刷新失败 '+repr(e))
                self.after(0,lambda:self.refresh_done(0,[],str(e)))
        threading.Thread(target=work,daemon=True).start()
    def refresh_done(self,n,w,error):
        self.load()
        if error:messagebox.showerror('联网刷新失败',error+'\n\n已记录到刷新日志。')
        else:messagebox.showinfo('联网请求完成',f'取得 {n} 场足球比赛。'+ ('\n部分联赛失败：\n'+'\n'.join(w) if w else '')+'\n\n注意：不代表中国体彩受注清单。')
    def import_csv(self):
        p=filedialog.askopenfilename(title='选择合法来源的体彩场次 CSV',filetypes=[('CSV 文件','*.csv')])
        if not p:return
        try:n=core.import_csv(p);self.load();messagebox.showinfo('导入成功',f'{n}场已导入。请自行核实来源和竞彩编号。')
        except Exception as e:core.log('CSV导入失败 '+repr(e));messagebox.showerror('导入失败',str(e))
    def export(self):
        p=filedialog.asksaveasfilename(title='保存研究报告',defaultextension='.html',initialfile='足球概率研究_'+self.day.get()+'.html',filetypes=[('网页报告','*.html')])
        if not p:return
        try:
            n=report.export(p,self.day.get())
            messagebox.showinfo('成功',f'报告已导出：{p}\n受注清单记录：{n}场')
        except Exception as e:messagebox.showerror('导出失败',str(e))
    def settings(self):
        c=refresh.read_config();w=tk.Toplevel(self);w.title('联网数据源配置');w.geometry('780x530');w.transient(self);w.grab_set()
        frm=ttk.Frame(w,padding=18);frm.pack(fill='both',expand=True)
        ttk.Label(frm,text='选择联网搜索来源',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(0,8))
        provider=tk.StringVar(value=c.get('provider','TheSportsDB（免费赛程）'))
        ttk.Combobox(frm,textvariable=provider,state='readonly',values=['TheSportsDB（免费赛程）','football-data.org（需Token）'],width=42).pack(anchor='w',pady=5)
        ttk.Label(frm,text='football-data.org Token（个人密钥，存储在此电脑配置文件中；仅用于联网获取数据）').pack(anchor='w',pady=(12,3))
        token=tk.StringVar(value=c.get('football_token',''))
        ttk.Entry(frm,textvariable=token,show='*',width=72).pack(fill='x')
        ttk.Label(frm,text='查询联赛代码（最多建议4个，免费额度有限）：PL,PD,BL1,SA,FL1,DED 等').pack(anchor='w',pady=(12,3))
        leagues=tk.StringVar(value=c.get('competitions','PL,PD,BL1,SA'))
        ttk.Entry(frm,textvariable=leagues).pack(fill='x')
        ttk.Label(frm,text='授权竞彩清单JSON接口 HTTPS URL（用于首个“竞彩受注场次”页面及11点自动同步）').pack(anchor='w',pady=(12,3))
        feed=tk.StringVar(value=c.get('feed_url',''))
        ttk.Entry(frm,textvariable=feed).pack(fill='x')
        ttk.Label(frm,text='授权竞彩清单接口 Token（如需；保存在本机，可使用环境变量 JINGCAI_FEED_TOKEN）').pack(anchor='w',pady=(8,2))
        feed_token=tk.StringVar(value=c.get('feed_token',''))
        ttk.Entry(frm,textvariable=feed_token,show='*').pack(fill='x')
        ttk.Label(frm,text='注意：TheSportsDB与football-data.org均不是体育彩票官方竞彩受注清单。\n免费接口、授权范围和可用比赛覆盖情况由供应商决定。',wraplength=730,foreground='#6c5360').pack(anchor='w',pady=14)
        def save():
            refresh.save_config({'provider':provider.get(),'football_token':token.get().strip(),'competitions':leagues.get().strip(),'feed_url':feed.get().strip(),'feed_token':feed_token.get().strip()});w.destroy();self.load()
        ttk.Button(frm,text='保存数据源设置',command=save).pack(anchor='e')
    def logs(self):
        w=tk.Toplevel(self);w.title('联网与定时刷新日志');w.geometry('920x480')
        t=tk.Text(w,wrap='word');t.pack(fill='both',expand=True)
        t.insert('1.0',core.LOG.read_text(encoding='utf-8')[-25000:] if core.LOG.exists() else '尚无日志');t.config(state='disabled')
    def open_data(self):
        core.DATA_DIR.mkdir(parents=True,exist_ok=True)
        if sys.platform=='win32':os.startfile(str(core.DATA_DIR))
        else:messagebox.showinfo('数据目录',str(core.DATA_DIR))
    def schedule(self):
        if sys.platform!='win32':messagebox.showinfo('仅Windows','本功能只能在Windows运行。');return
        if not getattr(sys,'frozen',False):messagebox.showinfo('需要EXE','请先用GitHub Actions生成 Windows EXE。');return
        exe=sys.executable
        # Windows Task Scheduler uses system local timezone. Detect Beijing UTC+08:00.
        if core.now().astimezone().utcoffset().total_seconds()!=8*3600:
            messagebox.showwarning('时区提示','本机系统时区不是UTC+8。Windows任务计划程序使用本机时区，设置11:00并非北京时间11:00。请调整Windows时区或手动调整任务时间。')
        cmd=['schtasks','/Create','/F','/SC','DAILY','/ST','11:00','/TN','JingcaiDeskDailyRefresh','/TR',f'"{exe}" --refresh']
        try:
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if r.returncode:raise RuntimeError((r.stderr or r.stdout).strip())
            messagebox.showinfo('成功','已创建每日11:00定时任务（按Windows系统时区）。电脑需开机联网；任务执行失败会写入日志。')
        except Exception as e:messagebox.showerror('创建失败',str(e))

if __name__=='__main__':
    if '--refresh' in sys.argv:sys.exit(refresh.headless())
    try:App().mainloop()
    except Exception:core.log(traceback.format_exc());raise
