// Copyright (C) 2021 Leigh Morresi (dgtlmoon@gmail.com)
// All rights reserved.
// yes - this is really a hack, if you are a front-ender and want to help, please get in touch!
//
// Refactored into a reusable factory: window.initVisualSelector(opts)
//   - edit.html drives it from stored screenshot + xpath-data URLs (auto-init at bottom of file)
//   - the Add Watch UI drives it from inline snapshot data fetched on demand
// Both share the same hover/highlight/select core.

window.initVisualSelector = function (opts) {
    // ---- DOM references (passed in, no globals) ----
    const $selectorCanvasElem = opts.$canvas;
    const $includeFiltersElem = opts.$includeFilters;
    const $selectorBackgroundElem = opts.$background;
    const $selectorCurrentXpathElem = opts.$xpathDisplay;          // the inner <span>
    const $fetchingUpdateNoticeElem = opts.$fetchingNotice || $();
    const $selectorWrapperElem = opts.$wrapper;
    const $clearSelectorElem = opts.$clearButton || $();

    // edit.html supplies an AJAX url for the element data; the add-watch UI supplies data inline
    const xpathDataUrl = opts.xpathDataUrl;
    const isImageProcessor = !!opts.processorIsImage;
    // Stored watch screenshots are DPR-1, so X scales by the screenshot's natural width.
    // The live browser-steps capture (used by Add Watch) may render at device-scale-factor != 1,
    // so its X must scale by the page's CSS width (browser_width) instead - exactly like
    // browser-steps.js does. Y always scales by the screenshot's natural height.
    const scaleByBrowserWidth = !!opts.scaleByBrowserWidth;

    // ---- state ----
    let runInClearMode = false;
    let selectionEnabled = opts.enableSelection !== false;
    let currentSelections = [];
    let currentSelection = null;
    let appendToList = false;
    let c, xctx, ctx;
    let xScale = 1, yScale = 1;
    let selectorImage, selectorImageRect, selectorData;
    let elementHandlers = {}; // Store references to element selection handlers (needed for draw mode toggling)

    // Box drawing mode variables (for image_ssim_diff processor)
    let drawMode = false;
    let isDrawing = false;
    let isDragging = false;
    let drawStartX, drawStartY;
    let dragOffsetX, dragOffsetY;
    let drawnBox = null;
    let resizeHandle = null;
    const HANDLE_SIZE = 8;

    // Color constants
    const FILL_STYLE_HIGHLIGHT = 'rgba(205,0,0,0.35)';
    const FILL_STYLE_GREYED_OUT = 'rgba(205,205,205,0.95)';
    const STROKE_STYLE_HIGHLIGHT = 'rgba(255,0,0, 0.9)';
    const FILL_STYLE_REDLINE = 'rgba(255,0,0, 0.1)';
    const STROKE_STYLE_REDLINE = 'rgba(225,0,0,0.9)';

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

    function applyElementData(data) {
        $fetchingUpdateNoticeElem.html(i18nT('vsRendering', "Rendering.."));
        selectorData = data;

        sortScrapedElementsBySize();
        console.log(`Reported browser width from backend: ${data['browser_width']}`);

        // Little sanity check for the user, alert them if something missing
        alertIfFilterNotFound();

        setScale();
        reflowSelector();

        // Initialize draw mode after everything is set up
        initializeDrawMode();

        $fetchingUpdateNoticeElem.fadeOut();
    }

    function updateFiltersText() {
        // Assuming currentSelections is already defined and contains the selections
        let uniqueSelections = new Set(currentSelections.map(sel => (sel[0] === '/' ? `xpath:${sel.xpath}` : sel.xpath)));

        if (currentSelections.length > 0) {
            // Convert the Set back to an array and join with newline characters
            let textboxFilterText = Array.from(uniqueSelections).join("\n");
            $includeFiltersElem.val(textboxFilterText);
        }
    }

    function setCurrentSelectedText(s) {
        // Selectors come from the scraped page, display them as text and never as markup
        $selectorCurrentXpathElem[0].textContent = s;
    }

    function drawHighlight(sel) {
        ctx.strokeRect(sel.left * xScale, sel.top * yScale, sel.width * xScale, sel.height * yScale);
        ctx.fillRect(sel.left * xScale, sel.top * yScale, sel.width * xScale, sel.height * yScale);
    }

    function handleMouseDown() {
        // If we are in 'appendToList' mode, grow the list, if not, just 1
        currentSelections = appendToList ? [...currentSelections, currentSelection] : [currentSelection];
        highlightCurrentSelected();
        updateFiltersText();
    }

    function reflowSelector() {
        $(window).off('resize.visualselector').on('resize.visualselector', () => {
            setScale();
            highlightCurrentSelected();
        });

        setScale();

        console.log(selectorData['size_pos'].length + " selectors found");

        let existingFilters = splitToList($includeFiltersElem.val());

        selectorData['size_pos'].forEach(sel => {
            if ((!runInClearMode && sel.highlight_as_custom_filter) || existingFilters.includes(sel.xpath)) {
                console.log("highlighting " + c);
                currentSelections.push(sel);
            }
        });

