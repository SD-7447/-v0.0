"""配置中心 v2：分层配置 + 运行时可改（管理后台更换 API KEY 的地基）。

优先级（高 → 低）：
1. 管理后台覆盖层  data/config.json   （运行时可改，无需重启）
2. 环境变量 / .env                     （部署默认值）
3. 代码内置默认值

密钥安全：读取接口对外返回时自动掩码；config.json 仅存在本机 data/ 目录（已被 .gitignore 排除）。
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OVERRIDES_PATH = DATA_DIR / "config.json"

_lock = threading.Lock()

# 允许从管理后台修改的键（白名单）
EDITABLE_KEYS = {
    "RECOGNIZER_PROVIDER",
    "QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL",
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
    "BOT_TOKEN",
}
SECRET_KEYS = {"QWEN_API_KEY", "DEEPSEEK_API_KEY", "BOT_TOKEN"}

_DEFAULTS = {
    "RECOGNIZER_PROVIDER": "mock",
    "QWEN_API_KEY": "",
    "QWEN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "QWEN_MODEL": "qwen-vl-max",
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
    "DEEPSEEK_MODEL": "deepseek-chat",
    "BOT_TOKEN": "",
    "SD_DB_PATH": str(DATA_DIR / "sd_finance.db"),
    "SD_UPLOAD_DIR": str(DATA_DIR / "uploads"),
    "SD_LOG_DIR": str(DATA_DIR / "logs"),
}


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _read_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if k in EDITABLE_KEYS}
    except (json.JSONDecodeError, OSError):
        return {}


def get(key: str) -> str:
    """读取生效配置：覆盖层 > 环境变量 > 默认值。"""
    overrides = _read_overrides()
    if key in overrides and overrides[key] != "":
        return overrides[key]
    return os.getenv(key, _DEFAULTS.get(key, ""))


def masked(key: str) -> str:
    """供管理后台展示的掩码值：sk-abc…xyz"""
    value = get(key)
    if key not in SECRET_KEYS or not value:
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]}"


def update_overrides(patch: dict[str, Any]) -> dict[str, str]:
    """写入管理后台覆盖层。空字符串 = 清除该键的覆盖（回退到 .env/默认）。"""
    with _lock:
        overrides = _read_overrides()
        for key, value in patch.items():
            if key not in EDITABLE_KEYS:
                raise KeyError(f"配置项 {key} 不允许从后台修改")
            value = str(value).strip()
            if value:
                overrides[key] = value
            else:
                overrides.pop(key, None)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    return _read_overrides()


@dataclass(frozen=True)
class Settings:
    """某一时刻的配置快照（由 get_settings() 生成）。"""

    recognizer_provider: str
    qwen_api_key: str
    qwen_base_url: str
    qwen_model: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    db_path: Path
    upload_dir: Path
    log_dir: Path


def get_settings() -> Settings:
    """每次调用生成最新快照——后台改 key 后立即生效，无需重启。"""
    s = Settings(
        recognizer_provider=get("RECOGNIZER_PROVIDER").lower(),
        qwen_api_key=get("QWEN_API_KEY"),
        qwen_base_url=get("QWEN_BASE_URL"),
        qwen_model=get("QWEN_MODEL"),
        deepseek_api_key=get("DEEPSEEK_API_KEY"),
        deepseek_base_url=get("DEEPSEEK_BASE_URL"),
        deepseek_model=get("DEEPSEEK_MODEL"),
        db_path=Path(get("SD_DB_PATH")),
        upload_dir=Path(get("SD_UPLOAD_DIR")),
        log_dir=Path(get("SD_LOG_DIR")),
    )
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    s.log_dir.mkdir(parents=True, exist_ok=True)
    return s


# 兼容旧代码：模块级快照仅用于启动期的路径初始化
settings = get_settings()
