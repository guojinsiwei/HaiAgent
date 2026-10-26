"""Fresh hidden input; SSH stdin only; no stored API credential or auto-relaunch."""
import json
import subprocess
import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
REMOTE = '/mnt/sdb/home/lizh639/tb4-kz-dsh-engineering-smoke3-20261015'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
       '-o', 'StrictHostKeyChecking=yes', '-i',
       'C:/Users/54177/.ssh/cubestudio_notebook', 'lizh639@172.16.108.236',
       REMOTE + '/venv/bin/python', REMOTE + '/campaign.py']
RECEIPT = ROOT / 'audit/launch-receipt.json'


def main():
    # Check before asking for a secret: a previous successful launch must never
    # produce a second credential prompt, even after the first window closes.
    check = subprocess.run(SSH, capture_output=True, timeout=60,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    if check.returncode:
        window = tk.Tk()
        window.withdraw()
        messagebox.showinfo('未打开凭据输入', '服务器未接受新的启动。可能已经启动；请检查状态，不要重复运行。', parent=window)
        window.destroy()
        return
    window = tk.Tk()
    window.title('KZ-on-DSH 独立三题小测 · TaoToken')
    window.geometry('600x265')
    window.attributes('-topmost', True)
    tk.Label(window, text='冻结前 3 题 · 并行 1 · 每次 10800 秒\n仅工程故障最后重试一次，最多 6 个试次\n模型 deepseek-flash；TaoToken Token Plan 接口',
             justify='left', font=('Microsoft YaHei', 11)).pack(padx=20, pady=15)
    tk.Label(window, text='输入本次 API Key（隐藏；不保存；通过 SSH 标准输入传递）').pack()
    entry = tk.Entry(window, show='*', width=65)
    entry.pack(padx=20, pady=10)
    status = tk.Label(window, text='已通过服务器无模型验收后，才允许启动。')
    status.pack()

    def start():
        key = entry.get().strip()
        if not key:
            status.config(text='请输入本次凭据，或关闭窗口取消。')
            return
        button.config(state='disabled')
        entry.delete(0, tk.END)
        status.config(text='正在验证封存并启动，勿重复点击……')
        window.update()
        try:
            result = subprocess.run(SSH + ['--launch'],
                                    input=(json.dumps({'key': key}) + '\n').encode(),
                                    capture_output=True, timeout=120,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            output = (result.stdout + result.stderr).decode(errors='replace').replace(key, '[REDACTED]')
            record = dict(exit_code=result.returncode, output=output,
                          state='acknowledged' if result.returncode == 0 else 'needs_inspection')
        except subprocess.TimeoutExpired:
            record = dict(state='unknown_requires_inspection', output='SSH launch acknowledgement timed out. Do not relaunch automatically.')
        except Exception as exc:
            record = dict(state='needs_inspection', output=type(exc).__name__)
        finally:
            key = ''
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        record['recorded_utc'] = stamp
        destination = RECEIPT.with_name('launch-receipt-' + stamp + '.json')
        destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        if not RECEIPT.exists():
            RECEIPT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        messagebox.showinfo('启动回执', record['output'] or record['state'], parent=window)
        window.destroy()

    button = tk.Button(window, text='使用本次凭据启动已确认的三题实验', command=start)
    button.pack(pady=10)
    entry.focus_set()
    window.mainloop()


if __name__ == '__main__':
    main()
