"""Native Windows experiment dashboard. Only allowlisted metadata is displayed."""
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from monitor import ROOT, DISPLAY, STATE, load_config, load_cache, poll, update_state, reconcile, save_cache

BG = '#101820'
PANEL = '#18232e'
TEXT = '#e5edf5'
MUTED = '#98aab9'
BLUE = '#78c5ff'
GREEN = '#76dfb1'
RED = '#ff979d'
AMBER = '#edc47d'


def clock(value):
    if not value:
        return '—'
    return dt.datetime.fromtimestamp(value, dt.timezone(dt.timedelta(hours=8))).strftime('%m-%d %H:%M:%S')


def duration(value):
    if value is None:
        return '—'
    value = int(max(0, value))
    return f'{value // 3600:02d}:{value % 3600 // 60:02d}:{value % 60:02d}'


def amount(value, maximum=None):
    if value is None:
        return '—'
    return f'{int(value)} / {int(maximum)}' if maximum else str(int(value))


class Dashboard:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.states = load_cache()
        self.events = queue.Queue()
        self.busy = False
        self.last_poll = 0
        self.next_poll = 0
        self.campaigns = {}
        self.selection = None
        self.history = tk.BooleanVar(value=False)
        self.running_only = tk.BooleanVar(value=False)
        self.interval = tk.StringVar(value=str(self.config.get('refresh_seconds', 15)))
        self.search = tk.StringVar()
        self._style()
        self._build()
        self.render()
        self.refresh()
        self.root.after(200, self.tick)

    def _style(self):
        self.root.title('实验进度 · CubeStudio / 计算节点')
        if (ROOT / 'monitor.ico').exists():
            self.root.iconbitmap(str(ROOT / 'monitor.ico'))
        self.root.configure(bg=BG)
        w = min(1320, self.root.winfo_screenwidth() - 80)
        h = min(940, self.root.winfo_screenheight() - 100)
        self.root.geometry(f'{w}x{h}+30+30')
        self.root.minsize(1000, 650)
        self.root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 22, 'bold'))
        style.configure('TButton', background='#263746', foreground=TEXT, borderwidth=0, padding=(14, 8))
        style.map('TButton', background=[('active', '#354e63'), ('disabled', PANEL)])
        style.configure('TCheckbutton', background=BG, foreground=TEXT)
        style.map('TCheckbutton', background=[('active', BG)])
        style.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=TEXT)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=6)
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=33, borderwidth=0, font=('Microsoft YaHei UI', 10))
        style.configure('Treeview.Heading', background='#243443', foreground=MUTED,
                        relief='flat', padding=(5, 9), font=('Microsoft YaHei UI', 10))
        style.map('Treeview', background=[('selected', '#294d69')], foreground=[('selected', TEXT)])
        style.configure('Horizontal.TProgressbar', troughcolor='#273b4c', background=GREEN, borderwidth=0)

    def _build(self):
        shell = ttk.Frame(self.root, padding=22)
        shell.pack(fill='both', expand=True)
        top = ttk.Frame(shell)
        top.pack(fill='x')
        title = ttk.Frame(top)
        title.pack(side='left')
        ttk.Label(title, text='实验进度', style='Title.TLabel').pack(anchor='w')
        ttk.Label(title, text='CubeStudio 与计算节点 · 自动发现恢复实验', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        self.refresh_button = ttk.Button(top, text='立即刷新', command=self.refresh)
        self.refresh_button.pack(side='right', padx=(10, 0))
        ttk.Button(top, text='保存快照', command=self.export).pack(side='right')

        self.node_row = ttk.Frame(shell)
        self.node_row.pack(fill='x', pady=(18, 14))
        self.node_labels = {}
        for node in self.config['nodes']:
            box = tk.Frame(self.node_row, bg=PANEL, padx=14, pady=11)
            box.pack(side='left', fill='x', expand=True, padx=(0, 10))
            tk.Label(box, text=node['name'], bg=PANEL, fg=TEXT, anchor='w',
                     font=('Microsoft YaHei UI', 11, 'bold')).pack(fill='x')
            label = tk.Label(box, text='正在连接…', bg=PANEL, fg=MUTED, anchor='w')
            label.pack(fill='x', pady=(5, 0))
            self.node_labels[node['id']] = label

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(toolbar, text='只看进行中', variable=self.running_only, command=self.render).pack(side='left')
        ttk.Checkbutton(toolbar, text='显示历史 / 节点快照', variable=self.history, command=self.render).pack(side='left', padx=14)
        ttk.Label(toolbar, text='筛选', style='Muted.TLabel').pack(side='left', padx=(14, 5))
        entry = ttk.Entry(toolbar, textvariable=self.search, width=18)
        entry.pack(side='left')
        self.search.trace_add('write', lambda *_: self.render())
        ttk.Label(toolbar, text='刷新间隔', style='Muted.TLabel').pack(side='right', padx=(12, 0))
        choice = ttk.Combobox(toolbar, textvariable=self.interval, values=('10', '15', '30', '60'), width=4, state='readonly')
        choice.pack(side='right')
        choice.bind('<<ComboboxSelected>>', lambda _: self.set_interval())
        ttk.Label(toolbar, text='秒', style='Muted.TLabel').pack(side='right', padx=5)

        panes = ttk.Panedwindow(shell, orient='vertical')
        panes.pack(fill='both', expand=True)
        upper = ttk.Frame(panes)
        lower = ttk.Frame(panes)
        panes.add(upper, weight=2)
        panes.add(lower, weight=5)
        columns = ('experiment', 'status', 'progress', 'active', 'pending', 'failed', 'mean', 'host')
        self.tree = ttk.Treeview(upper, columns=columns, show='headings', height=7, selectmode='browse')
        widths = (130, 250, 95, 65, 65, 90, 95, 180)
        for column, heading, width in zip(columns,
                ('实验', '状态', '已评分', '在跑', '排队', '待补跑', '已评均分', '运行 / 评分节点'), widths):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, minwidth=width // 2, stretch=column in ('status', 'host'),
                             anchor='w' if column in ('experiment', 'status', 'host') else 'center')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(upper, orient='vertical', command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)

        head = ttk.Frame(lower)
        head.pack(fill='x', pady=(17, 8))
        self.detail_title = ttk.Label(head, text='请选择实验', font=('Microsoft YaHei UI', 14, 'bold'))
        self.detail_title.pack(side='left')
        self.detail_counts = ttk.Label(head, text='', style='Muted.TLabel')
        self.detail_counts.pack(side='right')
        self.progress = ttk.Progressbar(lower, maximum=100)
        self.progress.pack(fill='x', pady=(0, 9))
        self.detail_info = ttk.Label(lower, text='正在读取远程元数据…', style='Muted.TLabel', wraplength=1100)
        self.detail_info.pack(fill='x', pady=(0, 9))

        task_frame = ttk.Frame(lower)
        task_frame.pack(fill='both', expand=True)
        cols = ('task', 'state', 'models', 'wire', 'tools', 'duration', 'age', 'result', 'node')
        self.tasks = ttk.Treeview(task_frame, columns=cols, show='headings', height=10)
        for column, heading, width in zip(cols,
                ('任务', '状态', '模型调用', '接口尝试', '命令', '已用时间', '最近活动', '得分 / 原因', '节点'),
                (195, 100, 95, 80, 90, 95, 100, 150, 145)):
            self.tasks.heading(column, text=heading)
            self.tasks.column(column, width=width, minwidth=60, stretch=column in ('task', 'result'),
                              anchor='w' if column in ('task', 'result', 'node') else 'center')
        self.tasks.pack(side='left', fill='both', expand=True)
        task_scroll = ttk.Scrollbar(task_frame, orient='vertical', command=self.tasks.yview)
        task_scroll.pack(side='right', fill='y')
        self.tasks.configure(yscrollcommand=task_scroll.set)
        for table in (self.tree, self.tasks):
            table.tag_configure('running', foreground=BLUE)
            table.tag_configure('graded', foreground=GREEN)
            table.tag_configure('failed', foreground=RED)
            table.tag_configure('stalled', foreground=AMBER)
            table.tag_configure('offline', foreground=MUTED)
        self.tasks.bind('<Double-1>', self.task_details)

        bottom = ttk.Frame(shell)
        bottom.pack(fill='x', pady=(12, 0))
        self.footer = ttk.Label(bottom, text='每 15 秒刷新；双击任务查看完整状态。', style='Muted.TLabel')
        self.footer.pack(side='left')
        ttk.Button(bottom, text='配置与说明', command=self.help).pack(side='right')
        self.root.bind('<F5>', lambda _: self.refresh())

    def set_interval(self):
        self.config = load_config()
        self.config['refresh_seconds'] = int(self.interval.get())
        self.next_poll = time.time() + int(self.interval.get())
        (ROOT / 'config.json').write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding='utf-8')

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.configure(text='刷新中…', state='disabled')
        self.last_poll = time.time()
        def work():
            try:
                for result in poll(self.config):
                    self.events.put(('node', result))
            except Exception:
                self.events.put(('error', '本轮采集未完成，请检查节点连接'))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=work, daemon=True).start()

    def tick(self):
        changed = False
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'node':
                update_state(self.states, value)
                changed = True
            elif kind == 'done':
                self.busy = False
                self.next_poll = time.time() + int(self.interval.get())
                self.refresh_button.configure(text='立即刷新', state='normal')
                try:
                    save_cache(self.states)
                except OSError:
                    self.footer.configure(text='快照缓存不可写；实时查询仍可使用')
            elif kind == 'error':
                self.footer.configure(text=value)
        if changed:
            self.render()
        if not self.busy and time.time() >= self.next_poll:
            self.refresh()
        if not self.busy:
            self.footer.configure(text=f'下次刷新 {max(0, int(self.next_poll - time.time()))} 秒 · 双击任务查看详情 · F5 刷新 · 已评均分在全部完成前仅代表已评分题')
        self.root.after(200, self.tick)

    def render(self):
        for node in self.config['nodes']:
            state = self.states.get(node['id'], {})
            if state.get('ok'):
                observed = state['data']['observed_at']
                text = f'● 在线  {clock(observed).split(" ")[-1]}  · {state.get("latency", 0):.1f}s'
                color = GREEN
            else:
                text = '○ ' + state.get('error', '正在连接…')
                if state.get('data'):
                    text += ' · 上次 ' + clock(state['data'].get('observed_at'))
                color = AMBER if state.get('data') else MUTED
            self.node_labels[node['id']].configure(text=text, fg=color)
        records = reconcile(self.states, history=self.history.get())
        self.campaigns = {c['id']: c for c in records}
        selected = self.selection
        self.tree.delete(*self.tree.get_children())
        text = self.search.get().strip().lower()
        visible = []
        for c in records:
            if self.running_only.get() and not (c['active_count'] or c['controller_alive'] or c['status'] == '正在评分'):
                continue
            title = DISPLAY.get(c['method'], c['method'])
            if self.history.get():
                title += ' · ' + Path(c['root']).name
            if text and text not in (title + ' ' + c['root']).lower():
                continue
            hosts = {t['node'] for t in c['tasks'] if t['state'] in ('running', 'stalled')}
            hosts.add(c['node'])
            hostnames = ', '.join(self.node_name(i, short=True) for i in sorted(hosts))
            tag = 'running' if c['active_count'] else 'graded' if c['graded_count'] == c['expected'] else 'failed' if c['failed_count'] else 'offline'
            if not c['connection_ok']:
                tag = 'offline'
            self.tree.insert('', 'end', iid=c['id'], values=(title, c['status'],
                f'{c["graded_count"]} / {c["expected"]}', c['active_count'], c['counts']['pending'],
                c['failed_count'], f'{c["mean"] * 100:.2f}%' if c['mean'] is not None else '—', hostnames), tags=(tag,))
            visible.append(c['id'])
        if selected not in visible:
            selected = visible[0] if visible else None
        self.selection = selected
        if selected:
            self.tree.selection_set(selected)
            self.show_details()
        else:
            self.tasks.delete(*self.tasks.get_children())
            self.detail_title.configure(text='没有匹配的实验' if self.states else '正在连接节点…')
            self.detail_info.configure(text='调整筛选条件，或等待首次采集完成。')
            self.detail_counts.configure(text='')
            self.progress['value'] = 0

    def select(self, _=None):
        values = self.tree.selection()
        if values:
            self.selection = values[0]
            self.show_details()

    def node_name(self, node_id, short=False):
        if short:
            return {'college': '计算节点', 'cube0': 'Cube 1', 'cube1': 'Cube 2'}.get(node_id, node_id)
        return next((n['name'] for n in self.config['nodes'] if n['id'] == node_id), node_id)

    def show_details(self):
        c = self.campaigns.get(self.selection)
        if not c:
            return
        self.detail_title.configure(text=DISPLAY.get(c['method'], c['method']) + ' · ' + c['status'])
        self.detail_counts.configure(text=f'已评分 {c["graded_count"]}/{c["expected"]}  · 完整成功 {c["successes"]}  · 本轮待补跑 {c["failed_count"]}')
        self.progress['value'] = c['graded_count'] / max(1, c['expected']) * 100
        errors = c.get('grading_errors', [])
        note = (' · 评分异常 ' + ', '.join(e.get('reason', '') for e in errors)) if errors else ''
        self.detail_info.configure(text=f'最近核实 {clock(c.get("observed_at"))}  · {c.get("model", "")}  · 输出上限 {c.get("output_tokens", "—")} tokens{note}\n{c["root"]}')
        self.tasks.delete(*self.tasks.get_children())
        self.visible_tasks = {}
        order = {'stalled': 0, 'running': 1, 'failed': 2, 'stopped': 2, 'interrupted': 2,
                 'awaiting_grade': 3, 'pending': 4, 'graded': 5}
        for index, task in enumerate(sorted(c['tasks'], key=lambda t: (order[t['state']], t['task']))):
            key = str(index)
            self.visible_tasks[key] = task
            result = f'{task["score"] * 100:.2f}%' if task.get('score') is not None else task.get('fault') or task.get('stop_reason') or '—'
            age = f'{int(task["age"])} 秒前' if task.get('age') is not None and task['state'] != 'graded' else '—'
            state = STATE[task['state']]
            if not task.get('connection_ok', c['connection_ok']):
                state += '（旧快照）'
            self.tasks.insert('', 'end', iid=key, values=(task['task'], state,
                amount(task.get('models'), task.get('model_limit')), amount(task.get('wire')),
                amount(task.get('tools'), task.get('tool_limit')), duration(task.get('seconds')),
                age, result, self.node_name(task['node'], short=True)),
                tags=(task['state'] if task['state'] in ('running', 'stalled', 'graded') else 'failed' if task['state'] in ('failed', 'stopped', 'interrupted') else 'offline',))

    def task_details(self, _=None):
        selected = self.tasks.selection()
        if not selected:
            return
        t = self.visible_tasks[selected[0]]
        messagebox.showinfo(t['task'], '\n'.join([
            f'状态：{STATE[t["state"]]}', f'节点：{self.node_name(t["node"])}',
            f'模型调用：{amount(t.get("models"), t.get("model_limit"))}',
            f'接口尝试：{amount(t.get("wire"))}', f'命令：{amount(t.get("tools"), t.get("tool_limit"))}',
            f'任务时间上限：{duration(t.get("wall_seconds"))}', f'最近活动：{clock(t.get("updated"))}',
            f'停止原因：{t.get("stop_reason") or "—"}', f'工程错误：{t.get("fault") or "—"}',
            f'评分记录：{t.get("score") if t.get("score") is not None else "尚未评分"}',
            '\n实验目录：' + t['source']]))

    def export(self):
        path = filedialog.asksaveasfilename(title='保存当前进度快照', defaultextension='.json',
            initialfile=dt.datetime.now().strftime('实验进度-%Y%m%d-%H%M%S.json'), filetypes=[('JSON', '*.json')])
        if path:
            Path(path).write_text(json.dumps({'exported_at': time.time(), 'nodes': self.states,
                'experiments': list(self.campaigns.values())}, indent=2, ensure_ascii=False), encoding='utf-8')

    def help(self):
        messagebox.showinfo('使用说明',
            '每 15 秒查询三个节点；F5 可立即刷新。\n\n'
            '默认显示五组实验的最新恢复版本，自动发现新目录。\n'
            'Cube 解题进程与计算节点评分记录合并显示。\n'
            '断线后保留上次快照并标记过期；不会将残留 running 状态当作存活进程。\n\n'
            '模型调用/接口尝试/命令来自任务记录。完整成功与提交/退出码是不同指标。\n'
            '已评均分在 20 题全部完成前仅代表已评分题。\n\n'
            'SSH 节点、目录扫描范围和刷新间隔可在程序目录 config.json 中修改。\n'
            '配置修改后重新打开程序。\n\n程序目录：' + str(ROOT))


def main():
    # Avoid duplicate desktop windows and duplicate polling after repeated clicks.
    mutex = None
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
        ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\LongCLIExperimentMonitor54177')
        if ctypes.windll.kernel32.GetLastError() == 183:
            user32 = ctypes.windll.user32
            user32.FindWindowW.restype = ctypes.c_void_p
            window = user32.FindWindowW(None, '实验进度 · CubeStudio / 计算节点')
            if window:
                user32.ShowWindow(ctypes.c_void_p(window), 9)
                user32.SetForegroundWindow(ctypes.c_void_p(window))
            return
    root = tk.Tk()
    try:
        Dashboard(root)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('实验进度', '程序启动失败：' + type(exc).__name__ + '\n请检查 config.json 和 SSH 连接。')
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(mutex))


if __name__ == '__main__':
    main()
