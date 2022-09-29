"""
Guards against cross-watch snapshot contamination in the filter/extract chain.

Watch checks run run_changedetection() on a shared ThreadPoolExecutor, so different watches
parse HTML in parallel threads. A single check mixes two lxml parsers - xpath_filter() has its
own, html_to_text() -> inscriptis uses lxml's process-global one. Without html_tools' lxml lock
those races corrupt libxml2 state and one document's rendered text lands in another's output.

Reported by a hosted customer whose snapshots contained an entirely different university's staff
directory concatenated ahead of their own, at double the normal size.

DOCS = {n: _make_doc(n) for n in NAMES}


def _assert_no_contamination(pipeline, jobs=JOBS):
    """Run pipeline concurrently over distinct docs; output must be byte-identical to the
    single-threaded result and must never contain another document's marker."""
    expected = {n: pipeline(DOCS[n]) for n in NAMES}
    problems = []
    lock = threading.Lock()

    def job(i):
        name = NAMES[i % len(NAMES)]
        out = pipeline(DOCS[name])
        found = [o for o in NAMES if o != name and f"{o}.example" in out]
        if found:
            with lock:
                problems.append(f"{name} snapshot contains {found} (len {len(out)}, "
                                f"expected {len(expected[name])})")
        elif out != expected[name]:
            with lock:
                problems.append(f"{name} non-deterministic output: len {len(out)}, "
                                f"expected {len(expected[name])}")

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        list(pool.map(job, range(jobs)))

    assert not problems, (
        f"{len(problems)} of {jobs} concurrent extractions were corrupted "
        f"(html_tools lxml guard broken?):\n  " + "\n  ".join(problems[:10])
    )


def test_xpath_filter_with_html_to_text_is_not_contaminated():
    """The customer's exact filter shape - this is the combination that reproduced."""
    def pipeline(doc):
        return html_tools.html_to_text(
            html_tools.xpath_filter("//table[contains(@class,'sidearm-table')]", doc,
                                    append_pretty_line_formatting=True))
    _assert_no_contamination(pipeline)


def test_xpath1_filter_with_html_to_text_is_not_contaminated():
    def pipeline(doc):
        return html_tools.html_to_text(
            html_tools.xpath1_filter("//table[contains(@class,'sidearm-table')]", doc,
                                     append_pretty_line_formatting=True))
    _assert_no_contamination(pipeline)


def test_subtractive_xpath_with_html_to_text_is_not_contaminated():
    def pipeline(doc):
        return html_tools.html_to_text(html_tools.element_removal(['//div[@class="ads"]'], doc))
    _assert_no_contamination(pipeline, jobs=JOBS_GUARD)


def test_css_filters_with_html_to_text_are_not_contaminated():
    """CSS goes through BeautifulSoup (pure Python, never libxml2) so this has always been
    safe - kept so a future move of CSS filtering onto lxml cannot regress silently."""
    def pipeline(doc):
        return html_tools.html_to_text(
            html_tools.include_filters("#staff", doc, append_pretty_line_formatting=True))
    _assert_no_contamination(pipeline, jobs=JOBS_GUARD)


