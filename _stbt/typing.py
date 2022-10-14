from typing import Optional, Tuple, TypeAlias, Union
import numpy.typing
from _stbt.mask import MaskTypes  # pylint: disable=unused-import

from _stbt.types import Region
from .imgutils import Color

KeyT : TypeAlias = str
FrameT : TypeAlias = numpy.typing.NDArray[numpy.uint8]

# Anything that load_image can take:
ImageT : TypeAlias = Union[numpy.typing.NDArray[numpy.uint8], str]

# None means no region
RegionT : TypeAlias = Optional[Region]

SizeT : TypeAlias = Tuple[int, int]

ColorT : TypeAlias = Union[Color, str, Tuple[int, int, int]]
