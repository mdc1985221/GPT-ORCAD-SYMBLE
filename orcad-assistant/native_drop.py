"""Windows file drop support without an extra drag/drop runtime dependency."""
import os


def enable_file_drop(root, on_files):
    if os.name != 'nt':
        return False
    if getattr(root, '_drop_callback', None) is not None:
        return True
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    pointer = ctypes.c_ssize_t
    callback_type = ctypes.WINFUNCTYPE(pointer, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    setter = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
    setter.argtypes = [wintypes.HWND, ctypes.c_int, pointer]
    setter.restype = pointer
    user32.CallWindowProcW.argtypes = [pointer, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = pointer
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    root.update_idletasks()
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    previous = None
    def handle(hwnd, message, wparam, lparam):
        if message == 0x82:  # WM_NCDESTROY: restore Tk's original window procedure.
            setter(hwnd, -4, previous)
            shell32.DragAcceptFiles(hwnd, False)
            return user32.CallWindowProcW(previous, hwnd, message, wparam, lparam)
        if message == 0x233:  # WM_DROPFILES
            paths = []
            try:
                count = shell32.DragQueryFileW(wparam, 0xffffffff, None, 0)
                for index in range(count):
                    length = shell32.DragQueryFileW(wparam, index, None, 0)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    shell32.DragQueryFileW(wparam, index, buffer, length + 1)
                    paths.append(buffer.value)
            finally:
                shell32.DragFinish(wparam)
            root.after(0, lambda: on_files(paths))
            return 0
        return user32.CallWindowProcW(previous, hwnd, message, wparam, lparam)
    callback = callback_type(handle)
    previous = setter(hwnd, -4, ctypes.cast(callback, ctypes.c_void_p).value)
    if not previous:
        return False
    # Keep callback alive until interpreter exits.
    root._drop_callback = callback
    shell32.DragAcceptFiles(hwnd, True)
    return True
