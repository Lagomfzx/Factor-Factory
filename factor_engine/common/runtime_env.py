from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return PROJECT_ROOT


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        value = value[1:-1]
    return key, value


# def load_dotenv_files() -> None:
#     for env_file in [PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"]:
#         if not env_file.exists() or not env_file.is_file():
#             continue
#         for line in env_file.read_text(encoding="utf-8").splitlines():
#             parsed = _parse_env_line(line)
#             if parsed is None:
#                 continue
#             key, value = parsed
#             if key not in os.environ:
#                 os.environ[key] = value
def load_dotenv_files() -> None:
    for env_file in [
        PROJECT_ROOT / "factor_factory.env",
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / ".env.local",
    ]:
        if not env_file.exists() or not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if key not in os.environ:
                os.environ[key] = value



def get_env(name: str, *, default: str | None = None, aliases: list[str] | None = None) -> str | None:
    candidate_names = [name] + list(aliases or [])
    for candidate in candidate_names:
        raw = os.getenv(candidate, "")
        if raw.strip():
            return raw.strip()
    return default


def require_env(name: str, *, aliases: list[str] | None = None, hint: str | None = None) -> str:
    value = get_env(name, aliases=aliases)
    if value is None or not value.strip():
        suffix = f" ({hint})" if hint else ""
        raise RuntimeError(f"Missing environment variable: {name}{suffix}")
    return value


def get_int_env(name: str, *, default: int, aliases: list[str] | None = None) -> int:
    value = get_env(name, aliases=aliases)
    if value is None:
        return default
    try:
        return int(value)
    except Exception as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got: {value}") from exc


def get_bool_env(name: str, *, default: bool, aliases: list[str] | None = None) -> bool:
    value = get_env(name, aliases=aliases)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"Environment variable {name} must be a boolean, got: {value}")


def get_platform_url() -> str:
    return get_env("FACTOR_FACTORY_PLATFORM_URL", default="http://localhost:8002") or "http://localhost:8002"
