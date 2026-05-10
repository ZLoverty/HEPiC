from HEPiC.__main__ import _show_startup_error, start_app


if __name__ == "__main__":
    try:
        start_app()
    except Exception as exc:
        _show_startup_error(exc)
        raise
