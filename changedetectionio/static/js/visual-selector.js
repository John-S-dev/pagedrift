// Copyright (C) 2021 Leigh Morresi (dgtlmoon@gmail.com)
// All rights reserved.
// yes - this is really a hack, if you are a front-ender and want to help, please get in touch!
//
// Refactored into a reusable factory: window.initVisualSelector(opts)
//   - edit.html drives it from stored screenshot + xpath-data URLs (auto-init at bottom of file)
//   - the Add Watch UI drives it from inline snapshot data fetched on demand
// Both share the same hover/highlight/select core.

        if (event.type === 'keydown') {
            if ($selectorBackgroundElem.is(":visible") && event.key === "Escape") {
                clearReset();
            }
        }
    });

    $clearSelectorElem.on('click', () => {
        clearReset();
    });

    // ---- public: (re)load a screenshot + element data into the selector ----
    // source = { screenshotSrc: <url|dataURI>, xpathData: <object|undefined> }
    function load(source) {
        currentSelections = [];
        runInClearMode = false;

        $selectorBackgroundElem
            .off("load error")
            .on("error", () => {
                $fetchingUpdateNoticeElem.html("<strong>Ooops!</strong> The VisualSelector tool needs at least one fetched page, please unpause the watch and/or wait for the watch to complete fetching and then reload this page.")
                    .css('color', '#bb0000');
                $('#selector-current-xpath, #clear-selector').hide();
            })
            .on('load', () => {
                console.log(`Loaded background ${$selectorBackgroundElem[0].naturalWidth}px`);
                // For the UI width of the whole edit area
                document.documentElement.style.setProperty('--visualselector-max-width', `${$selectorBackgroundElem[0].naturalWidth}px` );
                c = $selectorCanvasElem[0];
                xctx = c.getContext("2d");
                ctx = c.getContext("2d");
                // Drop any handlers left over from a previous load BEFORE (re)building the
                // selector - applyElementData() runs synchronously for inline xpathData and
                // binds the element handlers itself, so unbinding afterwards would silently
                // kill hover/click selection on the add-watch snapshot path.
                $selectorCanvasElem.off("mousemove mousedown mouseleave");
                if (source.xpathData) {
                    // Inline data (add-watch snapshot) - no extra round trip needed
                    applyElementData(source.xpathData);
                } else {
                    fetchData();
                }
            });

        // data: URIs must be used verbatim; real URLs get a cache-buster
        let src = source.screenshotSrc;
        if (src && src.indexOf('data:') !== 0) {
            src = `${src}?${new Date().getTime()}`;
        }
        $selectorBackgroundElem.attr("src", src);
    }

    function alertIfFilterNotFound() {
        let existingFilters = splitToList($includeFiltersElem.val());
        let sizePosXpaths = selectorData['size_pos'].map(sel => sel.xpath);

        for (let filter of existingFilters) {
            if (!sizePosXpaths.includes(filter)) {
                alert(`One or more of your existing filters was not found and will be removed when a new filter is selected.`);
                break;
            }
        }
    }

    function fetchData() {
        $fetchingUpdateNoticeElem.html(i18nT('vsFetching', "Fetching element data.."));

        $.ajax({
            url: xpathDataUrl,
            context: document.body
        }).done((data) => {
            applyElementData(data);
        });
    }

