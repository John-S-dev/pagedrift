"""
URL redirect validation module for preventing open redirect vulnerabilities.

This module provides functionality to safely validate redirect URLs, ensuring they:
1. Point to internal routes only (no external redirects)
2. Are properly normalized (preventing browser parsing differences)
3. Match registered Flask routes (no fake/non-existent pages)
4. Are fully logged for security monitoring

