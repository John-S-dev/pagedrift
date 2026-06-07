"""
LibVIPS implementation of ImageDiffHandler.

Uses pyvips for high-performance image processing with streaming architecture
and low memory footprint. Ideal for large screenshots (8000px+).
"""

from __future__ import annotations
import os
from typing import Tuple, Any, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    import pyvips

try:
    import pyvips
    PYVIPS_AVAILABLE = True
except ImportError:
    PYVIPS_AVAILABLE = False
    logger.warning("pyvips not available - install with: pip install pyvips")

from . import ImageDiffHandler


class LibvipsImageDiffHandler(ImageDiffHandler):
    """
    LibVIPS implementation using streaming architecture.

    Benefits:
    - 3x faster than ImageMagick
    - 5x less memory than PIL
    - Automatic multi-threading
    - Streaming - processes images in chunks
    """

    def __init__(self):
        if not PYVIPS_AVAILABLE:
            raise ImportError("pyvips is not installed. Install with: pip install pyvips")

    def load_from_bytes(self, img_bytes: bytes) -> pyvips.Image:
        """Load image from bytes using libvips streaming."""
        return pyvips.Image.new_from_buffer(img_bytes, '')

    def save_to_bytes(self, img: pyvips.Image, format: str = 'png', quality: int = 85) -> bytes:
        """
        Save image to bytes using temp file.

        Note: Uses temp file instead of write_to_buffer() to avoid C memory leak.
        See: https://github.com/libvips/pyvips/issues/234
        """
        import tempfile

        format = format.lower()

        try:
            if format == 'png':
                suffix = '.png'
                write_args = {'compression': 6}
            elif format in ['jpg', 'jpeg']:
                suffix = '.jpg'
                write_args = {'Q': quality}
            else:
                raise ValueError(f"Unsupported format: {format}")

            # Use temp file to avoid write_to_buffer() memory leak
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                temp_path = tmp.name

            # Write to file
            img.write_to_file(temp_path, **write_args)

            # Read bytes and clean up
            with open(temp_path, 'rb') as f:
                image_bytes = f.read()

            os.unlink(temp_path)
            return image_bytes

        except Exception as e:
            logger.error(f"Failed to save via temp file: {e}")
            # Fallback to write_to_buffer if temp file fails
            if format == 'png':
                return img.write_to_buffer('.png', compression=6)
            else:
                return img.write_to_buffer('.jpg', Q=quality)

    def crop(self, img: pyvips.Image, left: int, top: int, right: int, bottom: int) -> pyvips.Image:
        """Crop image using libvips."""
        width = right - left
        height = bottom - top
        return img.crop(left, top, width, height)

    def resize(self, img: pyvips.Image, max_width: int, max_height: int) -> pyvips.Image:
        """
        Resize image maintaining aspect ratio.

        Uses thumbnail_image for efficient downscaling with streaming.
        """
        width, height = img.width, img.height

        if width <= max_width and height <= max_height:
            return img

        # Calculate scaling to fit within max dimensions
        width_ratio = max_width / width if width > max_width else 1.0
        height_ratio = max_height / height if height > max_height else 1.0
        ratio = min(width_ratio, height_ratio)

        new_width = int(width * ratio)
        new_height = int(height * ratio)

        logger.debug(f"Resizing image: {width}x{height} -> {new_width}x{new_height}")

        # thumbnail_image is faster than resize for downscaling
        return img.thumbnail_image(new_width, height=new_height)

    def get_dimensions(self, img: pyvips.Image) -> Tuple[int, int]:
        """Get image dimensions."""
        return (img.width, img.height)

    def to_grayscale(self, img: pyvips.Image) -> pyvips.Image:
        """Convert to grayscale using 'b-w' colorspace."""
        return img.colourspace('b-w')

    def gaussian_blur(self, img: pyvips.Image, sigma: float) -> pyvips.Image:
        """Apply Gaussian blur."""
        if sigma > 0:
            return img.gaussblur(sigma)
        return img

    def absolute_difference(self, img1: pyvips.Image, img2: pyvips.Image) -> pyvips.Image:
        """
        Calculate absolute difference using operator overloading.

        LibVIPS supports arithmetic operations between images.
        """
        return (img1 - img2).abs()

    def threshold(self, img: pyvips.Image, threshold_value: int) -> Tuple[float, pyvips.Image]:
        """
        Apply threshold and calculate change percentage.

        Uses ifthenelse for efficient thresholding.
        """
        # Create binary mask: pixels above threshold = 255, others = 0
        mask = (img > threshold_value).ifthenelse(255, 0)

        # Calculate percentage by averaging mask values
        # avg() returns mean pixel value (0-255)
        # Divide by 255 to get proportion, multiply by 100 for percentage
        mean_value = mask.avg()
        change_percentage = (mean_value / 255.0) * 100.0

        return float(change_percentage), mask

    def apply_red_overlay(self, img: pyvips.Image, mask: pyvips.Image) -> bytes:
        """
        Apply red overlay where mask is True (50% blend).

        Args:
            img: Color image (will be converted to RGB if needed)
            mask: Binary mask (255 where changed, 0 elsewhere)

        Returns:
            JPEG bytes with red overlay
        """
        import tempfile

        # Ensure RGB colorspace
        if img.bands == 1:
            img = img.colourspace('srgb')

        # Normalize mask to 0-1 range for blending
        mask_normalized = mask / 255.0

