from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class ConfigurationError(RuntimeError):
    """필수 환경 설정이 없거나 올바르지 않을 때 발생한다."""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"필수 환경 변수 {name}이(가) 설정되지 않았습니다.")
    return value


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"환경 변수 {name}은(는) 정수여야 합니다.") from exc

    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"환경 변수 {name}은(는) {minimum}~{maximum} 범위여야 합니다."
        )
    return value


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    user: str
    password: str
    connect_timeout: int
    read_timeout: int

    @classmethod
    def from_environment(cls) -> "DatabaseSettings":
        return cls(
            host=_required_env("DB_HOST"),
            port=_int_env("DB_PORT", 3306, 1, 65535),
            user=_required_env("DB_USER"),
            password=_required_env("DB_PASSWORD"),
            connect_timeout=_int_env("DB_CONNECT_TIMEOUT", 5, 1, 30),
            read_timeout=_int_env("DB_READ_TIMEOUT", 10, 1, 60),
        )


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings.from_environment()

