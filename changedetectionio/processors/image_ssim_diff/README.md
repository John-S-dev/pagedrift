# Fast Screenshot Comparison Processor

Visual/screenshot change detection using ultra-fast image comparison algorithms.

## Overview

This processor uses **OpenCV** by default for screenshot comparison, providing **50-100x faster** performance compared to the previous SSIM implementation while still detecting meaningful visual changes.

## Current Features

- **Ultra-fast OpenCV comparison**: cv2.absdiff with Gaussian blur for noise reduction
- **MD5 pre-check**: Fast identical image detection before expensive comparison
- **Configurable sensitivity**: Threshold-based change detection
- **Three-panel diff view**: Previous | Current | Difference (with red highlights)
- **Direct image support**: Works with browser screenshots AND direct image URLs
- **Visual selector support**: Compare specific page regions using CSS/XPath selectors
- **Download images**: Download any of the three comparison images directly from the diff view

## Performance

- **OpenCV (default)**: 50-100x faster than SSIM
- **Large screenshots**: Automatic downscaling for diff visualization (configurable via `MAX_DIFF_HEIGHT`/`MAX_DIFF_WIDTH`)
- **Memory efficient**: Explicit cleanup of large objects for long-running processes
- **JPEG diff images**: Smaller file sizes, faster rendering

## How It Works

1. **Fetch**: Screenshot captured via browser OR direct image URL fetched
2. **MD5 Check**: Quick hash comparison - if identical, skip comparison
3. **Region Selection** (optional): Crop to specific page region if visual selector is configured
4. **OpenCV Comparison**: Fast pixel-level difference detection with Gaussian blur
5. **Change Detection**: Percentage of changed pixels above threshold = change detected
6. **Visualization**: Generate diff image with red-highlighted changed regions

## Architecture

### Default Method: OpenCV

The processor uses OpenCV's `cv2.absdiff()` for ultra-fast pixel-level comparison:

```python
# Convert to grayscale
gray_from = cv2.cvtColor(image_from, cv2.COLOR_RGB2GRAY)
gray_to = cv2.cvtColor(image_to, cv2.COLOR_RGB2GRAY)

# Apply Gaussian blur (reduces noise, controlled by OPENCV_BLUR_SIGMA env var)
gray_from = cv2.GaussianBlur(gray_from, (0, 0), sigma=0.8)
gray_to = cv2.GaussianBlur(gray_to, (0, 0), sigma=0.8)

# Calculate absolute difference
diff = cv2.absdiff(gray_from, gray_to)

# Apply threshold (default: 30)
_, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

# Count changed pixels
change_percentage = (changed_pixels / total_pixels) * 100
```

### Optional: Pixelmatch

For users who need better anti-aliasing detection (especially for text-heavy screenshots), **pixelmatch** can be optionally installed:

```bash
pip install pybind11-pixelmatch>=0.1.3
```

**Note**: Pixelmatch uses a C++17 implementation via pybind11 and may have build issues on some platforms (particularly Alpine/musl systems with symbolic link security restrictions). The application will automatically fall back to OpenCV if pixelmatch is not available.

