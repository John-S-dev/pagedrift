"""
Subprocess-isolated image operations for memory leak prevention.

LibVIPS accumulates C-level memory in long-running processes that cannot be
reclaimed by Python's GC or libvips cache management. Using subprocess isolation
ensures complete memory cleanup when the process exits.

This module wraps LibvipsImageDiffHandler operations in multiprocessing for
complete memory isolation without code duplication.

Research: https://github.com/libvips/pyvips/issues/234
"""

import multiprocessing

# CRITICAL: Use 'spawn' context instead of 'fork' to avoid inheriting parent's
# LibVIPS threading state which can cause hangs in gaussblur operations
# https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods


def generate_diff_isolated(img_bytes_from, img_bytes_to, threshold, blur_sigma, max_width, max_height):
    """
    Generate diff visualization in isolated subprocess for memory leak prevention.

    Args:
        img_bytes_from: Previous screenshot bytes
        img_bytes_to: Current screenshot bytes
        threshold: Pixel difference threshold
        blur_sigma: Gaussian blur sigma
        max_width: Maximum width for diff
        max_height: Maximum height for diff

    Returns:
        bytes: JPEG diff image or None on failure
    """
    ctx = multiprocessing.get_context('spawn')
    parent_conn, child_conn = ctx.Pipe()

    p = ctx.Process(
        target=_worker_generate_diff,
        args=(child_conn, img_bytes_from, img_bytes_to, threshold, blur_sigma, max_width, max_height)
    )
    p.start()

    result = None
    try:
        # Wait for result (30 second timeout)
        if parent_conn.poll(30):
            result = parent_conn.recv()
    except Exception as e:
        print(f"[Parent] Error receiving result: {e}", flush=True)
    finally:
        # Always close pipe first
        try:
            parent_conn.close()
        except:
            pass

        # Try graceful shutdown
        p.join(timeout=5)
        if p.is_alive():
            print("[Parent] Process didn't exit gracefully, terminating", flush=True)
            p.terminate()
            p.join(timeout=3)

        # Force kill if still alive
        if p.is_alive():
            print("[Parent] Process didn't terminate, killing", flush=True)
            p.kill()
            p.join(timeout=1)

    return result


