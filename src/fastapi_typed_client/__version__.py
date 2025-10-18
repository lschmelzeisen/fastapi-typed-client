from importlib.metadata import version
from typing import cast

__version__ = version(cast(str, __package__))
