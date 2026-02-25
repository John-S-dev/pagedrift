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

