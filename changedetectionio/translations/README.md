# Translators Guide

This document is for contributors who write templates (HTML) and for translators who maintain `.po` files.
It exists because fragmented `msgid`s — splitting a single sentence across multiple `_()` calls — cause
systematic translation breakage across many languages. Follow the patterns here to prevent that.

---

## Terminology

- **Always use "monitor" or "watcher"** for the concept of watching a URL — never the bare word "watch",
  which translates to "clock" (e.g. `hodinky` in Czech, `시계` in Korean, `時計` in Japanese).
- Use the **shortest suitable wording** for each language. If a language naturally uses the English
  derivative, prefer that.

---

## Template rules: do not fragment `msgid`s

