"""
CryptoPulse 配置管理
使用 os.environ + dataclass 简化，避免 pydantic-settings 依赖
自动加载 .env 文件（手动解析，无第三方依赖）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


def _load_env_file(env_path: str = ".env") -> None:
    """手动加载 .env 文件到 os.environ（无 python-dotenv 依赖）"""
    env_file = Path(env_path)
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and not os.environ.get(key):
                os.environ[key] = value


# 启动时加载 .env（在 Settings 实例化之前）
_load_env_file()


class TradingStyle(str, Enum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Settings:
    """应用配置，通过环境变量覆盖"""

    # OKX
    okx_api_key: str = field(default_factory=lambda: os.getenv("OKX_API_KEY", ""))
    okx_secret_key: str = field(default_factory=lambda: os.getenv("OKX_SECRET_KEY", ""))
    okx_passphrase: str = field(default_factory=lambda: os.getenv("OKX_PASSPHRASE", ""))
    okx_use_demo: bool = field(
        default_factory=lambda: os.getenv("OKX_USE_DEMO", "true").lower() == "true"
    )

    # AI
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    ai_model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "deepseek-chat"))

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))

    # 交易
    default_style: TradingStyle = TradingStyle.SHORT_TERM
    default_symbol: str = "BTC-USDT-SWAP"
    risk_per_trade: float = 0.02
    max_position_pct: float = 0.5

    # 日志
    log_level: LogLevel = LogLevel.INFO
    log_file: str = "logs/cryptopulse.log"

    # 代理（格式: http://127.0.0.1:10808 或 socks5://127.0.0.1:10808）
    proxy: str = field(default_factory=lambda: os.getenv("PROXY", ""))
    proxy_type: str = field(default_factory=lambda: os.getenv("PROXY_TYPE", "http"))

    @property
    def okx_ws_url(self) -> str:
        if self.okx_use_demo:
            return "wss://ws.okx.bet:8443/ws/v5/public?brokerId=9999"
        return "wss://ws.okx.com:8443/ws/v5/public"

    @property
    def okx_ws_url_production(self) -> str:
        """始终使用生产 WebSocket URL（绕过 demo 限制）"""
        return "wss://ws.okx.com:8443/ws/v5/public"

    @property
    def okx_rest_base(self) -> str:
        if self.okx_use_demo:
            return "https://www.okx.bet"
        return "https://www.okx.com"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 全局单例
settings = Settings()

# 项目目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
