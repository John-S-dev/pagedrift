/**
 * Unlock Element Dimensions After Screenshot Capture
 *
 * This script removes the inline !important styles that were applied by lock-elements-sizing.js
 * and restores elements to their original state using the WeakMap created during locking.
 *
 * USAGE:
 * Execute this script AFTER completing screenshot capture and restoring the viewport.
 * This allows the page to return to its normal responsive behavior.
 *
 * WHAT THIS SCRIPT DOES:
 * 1. Iterates through every element that was locked
 * 2. Reads original style values from the global WeakMap
 * 3. Restores original inline styles (or removes them if they weren't set originally)
 * 4. Cleans up the WeakMap
 *
 * @see lock-elements-sizing.js for the locking mechanism
 */

