"""Capture this app's own window for layout QA, then close it."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tkinter as tk
from unittest.mock import patch
import ctypes
from ctypes import wintypes
from PIL import Image, ImageGrab

def capture_window(root, target):
    """Render only our own window; never capture unrelated foreground content."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                              wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    hwnd, width, height = root.winfo_id(), root.winfo_width(), root.winfo_height()
    source = user32.GetDC(hwnd)
    memory = gdi32.CreateCompatibleDC(source)
    bitmap = gdi32.CreateCompatibleBitmap(source, width, height)
    previous = gdi32.SelectObject(memory, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory, 1):
            raise RuntimeError('Own-window rendering failed')
        gdi32.SelectObject(memory, previous)
        # BITMAPINFOHEADER with a negative height requests top-down BGRA pixels.
        header = ctypes.create_string_buffer(40)
        import struct
        struct.pack_into('<IiiHHIIiiII', header, 0, 40, width, -height,
                         1, 32, 0, width*height*4, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(width*height*4)
        if gdi32.GetDIBits(memory, bitmap, 0, height, pixels, header, 0) != height:
            raise RuntimeError('Own-window pixel extraction failed')
        Image.frombytes('RGB', (width, height), pixels.raw, 'raw', 'BGRX').save(target)
    finally:
        gdi32.SelectObject(memory, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, source)
root_path=Path(__file__).resolve().parent
loader=importlib.machinery.SourceFileLoader('monitor_gui',str(root_path/'app.pyw'))
spec=importlib.util.spec_from_loader(loader.name,loader);gui=importlib.util.module_from_spec(spec);loader.exec_module(gui)
root=tk.Tk()
root.attributes('-topmost', True)
with patch.object(gui.Dashboard,'refresh',lambda *_:None):
    app=gui.Dashboard(root)
    for state in app.states.values():state['ok']=True
    app.render()
    def capture():
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetForegroundWindow.restype = wintypes.HWND
        own_window = user32.GetAncestor(root.winfo_id(), 2)
        if user32.GetForegroundWindow() != own_window:
            root.destroy()
            raise RuntimeError('QA window is not foreground; refusing screen capture')
        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x+root.winfo_width(), y+root.winfo_height())).save(root_path/'ui-preview.png')
        root.destroy()
    root.after(100, lambda: (root.lift(), root.focus_force()))
    root.after(1600,capture)
    root.mainloop()
