from __future__ import annotations

from typing import Tuple, TypeAlias, Union

import numpy.typing


KeyT : TypeAlias = str
FrameT : TypeAlias = numpy.typing.NDArray[numpy.uint8]

# Anything that load_image can take:
ImageT : TypeAlias = Union[numpy.typing.NDArray[numpy.uint8], str]

PositionT : TypeAlias = Tuple[int, int]
SizeT : TypeAlias = Tuple[int, int]
