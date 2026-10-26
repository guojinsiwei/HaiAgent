"""User enters a fresh credential in a masked field; SSH stdin only."""
import datetime
import json
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
REMOTE = '/mnt/sdb/home/lizh639/tb2-native-kz-ten10-20261016'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
       '-o', 'StrictHostKeyChecking=yes', '-i',
       'C:/Users/54177/.ssh/cubestudio_notebook', 'lizh639@172.16.108.236',
       REMOTE + '/venv/bin/python', REMOTE + '/campaign.py']
AUDIT = ROOT / 'audit'


def save(record):
    AUDIT.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    record['recorded_utc'] = stamp
    data = json.dumps(record, ensure_ascii=False, indent=2)
    (AUDIT / ('launch-receipt-' + stamp + '.json')).write_text(data, encoding='utf-8')
    (AUDIT / 'launch-status.json').write_text(data, encoding='utf-8')


def main():
    window = tk.Tk()
    window.withdraw()
    try:
        check = subprocess.run(SSH, capture_output=True, timeout=60,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        if check.returncode:
            raise RuntimeError('Precheck failed')
    except Exception:
        save(dict(state='precheck_failed'))
        messagebox.showinfo('暂不能启动', '服务器未接受新启动。请检查状态，不要重复提交密钥。', parent=window)
        window.destroy()
        return
    window.title('TB2.0 · 原生 KZ 独立十题实验')
    window.geometry('680x330')
    window.deiconify()
    window.attributes('-topmost', True)
    tk.Label(window, text='原生 KZ2.0 · 同一批 10 题 · 单独运行 10 次 · 并行 1\n每次最多 120 次请求 / 180 次工具调用 / 45 分钟\n峰值单价估算保护：每次 4 元，新增独立 40 元（不是 Credits 精确上限）\ndeepseek-flash · TaoToken Token Plan 接口',
             justify='left', font=('Microsoft YaHei', 11)).pack(padx=20, pady=15)
    tk.Label(window, text='输入本轮 API Key（隐藏输入，不保存到文件，通过 SSH 标准输入传递）').pack()
    entry = tk.Entry(window, show='*', width=70)
    entry.pack(padx=20, pady=10)
    status = tk.Label(window, text='离线验收已通过。点击启动后才会调用模型。')
    status.pack()

    def start():
        key = entry.get().strip()
        if not key:
            status.config(text='请输入本轮密钥，或关闭窗口取消。')
            return
        button.config(state='disabled')
        entry.delete(0, tk.END)
        status.config(text='正在启动，请勿重复操作……')
        window.update()
        try:
            result = subprocess.run(SSH + ['--launch'],
                                    input=(json.dumps({'key': key}) + '\n').encode(),
                                    capture_output=True, timeout=120,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            output = (result.stdout + result.stderr).decode(errors='replace').replace(key, '[REDACTED]')
            record = dict(state='acknowledged' if result.returncode == 0 else 'needs_inspection',
                          exit_code=result.returncode, output=output)
        except subprocess.TimeoutExpired:
            record = dict(state='unknown_requires_inspection', output='启动回执超时；请先检查服务器，不要重复启动。')
        except Exception as exc:
            record = dict(state='needs_inspection', output=type(exc).__name__)
        finally:
            key = ''
        save(record)
        messagebox.showinfo('启动回执', record['output'] or record['state'], parent=window)
        window.destroy()

    button = tk.Button(window, text='输入密钥并启动原生 KZ 10 题', command=start)
    button.pack(pady=12)
    save(dict(state='waiting_for_key', model_calls=0))
    entry.focus_set()
    window.mainloop()


if __name__ == '__main__':
    main()
