import socket

from fastapi import APIRouter

router = APIRouter()


def _local_ip() -> str | None:
    """Best-effort IP the device would use to reach the LAN (its WiFi address on the Pi)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


@router.get("/info")
def get_info():
    return {
        "hostname": socket.gethostname(),
        "ip_address": _local_ip(),
    }
