import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    hepic_host: str = "127.0.0.1"
    hepic_tcp_port: int = 10001
    klipper_host: str = "127.0.0.1"
    klipper_port: int = 7125
    sensor_broadcast_interval: float = 0.1


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = Path(__file__).parent.parent / "config.json"
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = Config.__dataclass_fields__
    return Config(**{k: v for k, v in data.items() if k in fields})
