import sys
import traceback


def _early_error(exc):
    message = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "HEPiC startup error", 0x10)
    except Exception:
        print(message, file=sys.stderr)


try:
    from HEPiC.__main__ import _show_startup_error, start_app
except Exception as exc:
    _early_error(exc)
    sys.exit(1)


if __name__ == "__main__":
    try:
        start_app()
    except Exception as exc:
        _show_startup_error(exc)
        raise
