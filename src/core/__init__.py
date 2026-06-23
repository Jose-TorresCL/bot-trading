"""
Core package for trading bot.
Exposes key submodules for convenient imports: config_estrategias, backtesting, estrategias_bot1, utilidades.
"""

# Re-export commonly used modules (optional, keeps import style flexible)
from . import config_estrategias  # noqa: F401
from . import backtesting  # noqa: F401
from . import estrategias_bot1  # noqa: F401
from . import utilidades  # noqa: F401

__all__ = [
    "config_estrategias",
    "backtesting",
    "estrategias_bot1",
    "utilidades",
]
