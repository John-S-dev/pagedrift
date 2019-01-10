"""
OpenCV-based subprocess isolation for image comparison.

OpenCV is much more stable in multiprocessing contexts than LibVIPS.
No threading issues, no fork problems, picklable functions.
"""

# Public implementation name for logging
IMPLEMENTATION_NAME = "OpenCV"


