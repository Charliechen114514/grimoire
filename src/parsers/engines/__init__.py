"""Web 解析引擎注册表 + 自动发现。

内置引擎：wolai、static、playwright
自定义引擎：通过 --engine /path/to/my_engine.py 加载

用法：
    from src.parsers.engines import get_engine, detect_engine
    engine = get_engine("wolai")
    engine = detect_engine("https://www.wolai.com/xxx")
"""

import importlib
import importlib.util
import sys
from pathlib import Path

from src.log import logger

from .base import BaseWebEngine

# ── 内置引擎注册表 ─────────────────────────────────────────────────────

_REGISTRY: dict[str, type[BaseWebEngine]] = {}


def _register_builtin_engines() -> None:
    """自动扫描 engines/ 目录，注册所有 BaseWebEngine 子类。"""
    engines_dir = Path(__file__).parent
    for py_file in engines_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue

        module_name = f"src.parsers.engines.{py_file.stem}"
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            logger.warning("Failed to import engine {}: {}", module_name, e)
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseWebEngine)
                and attr is not BaseWebEngine
                and attr.NAME
            ):
                _REGISTRY[attr.NAME] = attr
                logger.debug("Registered engine: {} ({})", attr.NAME, attr.__name__)


def _load_external_engine(path: str) -> type[BaseWebEngine]:
    """从外部 .py 文件加载引擎。"""
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Engine file not found: {file_path}")

    module_name = f"_custom_engine_{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load engine from {file_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    # 查找 BaseWebEngine 子类
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseWebEngine)
            and attr is not BaseWebEngine
            and attr.NAME
        ):
            return attr

    raise ValueError(
        f"No BaseWebEngine subclass found in {file_path}. "
        f"Define a class with NAME attribute."
    )


def get_engine(
    name: str, *, external_path: str | None = None, **kwargs,
) -> BaseWebEngine:
    """获取引擎实例。

    Args:
        name: 引擎名称（如 "wolai"）或外部 .py 文件路径
        external_path: 外部引擎文件路径（已废弃，直接传路径到 name）
        **kwargs: 传递给引擎构造函数的配置
    """
    # 如果 name 是 .py 文件路径，加载外部引擎
    if name.endswith(".py") or external_path:
        path = external_path or name
        engine_cls = _load_external_engine(path)
        return engine_cls(**kwargs)

    if not _REGISTRY:
        _register_builtin_engines()

    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown engine '{name}'. Available: {available}. "
            f"Or pass a .py file path for custom engines."
        )

    return _REGISTRY[name](**kwargs)


def detect_engine(url: str) -> type[BaseWebEngine] | None:
    """根据 URL 自动检测匹配的引擎。

    Returns:
        匹配的引擎类，或 None（回退到 static）
    """
    if not _REGISTRY:
        _register_builtin_engines()

    for engine_cls in _REGISTRY.values():
        if engine_cls.DOMAINS and engine_cls.can_handle(url):
            return engine_cls

    return None


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称。"""
    if not _REGISTRY:
        _register_builtin_engines()
    return sorted(_REGISTRY.keys())
