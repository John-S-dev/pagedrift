// Restock price/stock timeline - a hand-rolled smoothed SVG line graph.
// Line segments are green where the item was in stock and red where it was out of stock.
//
// Two consumers:
//   * the restock diff page (#restock-graph), which fetches window.restock_data_url and also
//     builds the data table below it; and
//   * the watchlist inline roll-down, which calls window.renderRestockGraph(el, series, currency, i18n).
//
// Series shape (oldest -> newest): [{timestamp: <epoch sec>, price: <float|null>, in_stock: <bool|null>}]

(function ($) {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const COLOR_IN = '#1fa463';   // in stock = green
    const COLOR_OUT = '#e74c3c';  // out of stock = red
    const COLOR_UNKNOWN = '#999'; // stock state not known
    const HEIGHT = 320;          // default (diff page); the inline watchlist graph passes a shorter one
    const PAD = { top: 20, right: 16, bottom: 30, left: 52 };
    const MAX_X_LABELS = 6;       // keep the date axis uncluttered

    const DEFAULT_I18N = { in_stock: 'In stock', out_of_stock: 'Out of stock',
        no_data: 'No price data available to graph yet.', load_error: 'Could not load price history.',
        changes: 'Changes', avg_price: 'Average price',
        price_low: 'Currently low', price_typical: 'Currently typical', price_high: 'Currently high',
        // {pct} is substituted with an already-formatted percentage, e.g. "80%". The percent sign is
        // NOT part of the msgid on purpose: a bare "%" followed by a letter (" of") parses as a
        // python-format conversion ("% o"), which makes pybabel reject any translation of it.
        cheaper_than: 'cheaper than {pct} of tracked prices',
        pricier_than: 'more expensive than {pct} of tracked prices',
        typical_note: 'around the usual price', avg_label: 'avg' };
    const OVERLAY_MIN_POINTS = 5; // need enough history for low/typical/high to be meaningful

    function el(name, attrs) {
        const e = document.createElementNS(SVG_NS, name);
        for (const k in attrs) e.setAttribute(k, attrs[k]);
        return e;
    }

    function stockColor(inStock) {
        if (inStock === true) return COLOR_IN;
        if (inStock === false) return COLOR_OUT;
        return COLOR_UNKNOWN;
    }

    // X-axis label: day + short month + short year, e.g. "21 Jun '25".
    function fmtAxisDate(epoch) {
        const d = new Date(epoch * 1000);
        const dm = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
        return `${dm} '${String(d.getFullYear()).slice(-2)}`;
    }

    function fmtDateTime(epoch) {
        // undefined locale => the browser's locale; explicit options for a clean, complete format.
        return new Date(epoch * 1000).toLocaleString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
    }

    function fmtPrice(v, currency) {
        const n = Math.round(v * 100) / 100;
        return (currency || '') + (Number.isInteger(n) ? n : n.toFixed(2));
    }

    // Thin a large price series down to ~target points for drawing (you can't perceive more
    // points than pixels). Always keeps the first, last and the true min/max points so the line
    // still touches its extremes. The axis range + summary stay computed over the FULL data.
    function downsample(arr, target) {
        if (arr.length <= target) return arr;
        const keep = new Set([0, arr.length - 1]);
        let minI = 0, maxI = 0;
        for (let i = 1; i < arr.length; i++) {
            if (arr[i].price < arr[minI].price) minI = i;
            if (arr[i].price > arr[maxI].price) maxI = i;
        }
        keep.add(minI); keep.add(maxI);
        const step = arr.length / target;
        for (let i = 0; i < target; i++) keep.add(Math.floor(i * step));
        return Array.from(keep).sort((a, b) => a - b).map(i => arr[i]);
    }

    // Monotone cubic spline (Fritsch–Carlson). A gentle, smooth curve that — unlike Catmull-Rom —
    // is guaranteed NOT to overshoot beyond the actual data points: tangents are clamped so the
    // line never dips below / rises above neighbouring values. So the curve stays faithful to the
    // real prices (no phantom dips/spikes) while still looking soft. Returns an SVG path string.
    function monotonePath(pts) {
        const n = pts.length;
        if (n < 2) return '';
        const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
        if (n === 2) return `M ${xs[0].toFixed(1)} ${ys[0].toFixed(1)} L ${xs[1].toFixed(1)} ${ys[1].toFixed(1)}`;

        const ticks = [dataMax, (dataMin + dataMax) / 2, dataMin];

        // Widen the left gutter to fit the price labels (e.g. "CZK12.34") so a long currency
        // prefix isn't clipped at the SVG's left edge. ~7px/char + padding.
        const maxLabelChars = Math.max.apply(null, ticks.map(v => fmtPrice(v, currency).length));
        const padLeft = Math.max(PAD.left, maxLabelChars * 7 + 14);

        const innerW = width - padLeft - PAD.right;
        // Draw at most ~one point per few pixels; keeps the SVG light on long histories / mobile.
        const drawData = downsample(data, Math.max(40, Math.min(250, Math.floor(innerW / 4))));
        const x = i => padLeft + (i * innerW) / (drawData.length - 1);
        const y = price => PAD.top + (1 - (price - domMin) / range) * innerH;
        const pts = drawData.map((p, i) => ({ x: x(i), y: y(p.price), d: p }));

        // Size the SVG in real pixels at the measured width (no viewBox => no CSS rescaling).
        const svg = el("svg", { width: width, height: height, role: "img" });

        // Y axis: max / mid / min gridlines + price labels.
        ticks.forEach(price => {
            const yy = y(price);
            svg.appendChild(el('line', { class: 'rg-axis', x1: padLeft, y1: yy, x2: width - PAD.right, y2: yy, opacity: price === dataMin ? 0.6 : 0.15 }));
            const t = el('text', { class: 'rg-label', x: padLeft - 8, y: yy + 4, 'text-anchor': 'end' });
            t.textContent = fmtPrice(price, currency);
            svg.appendChild(t);
        });

        // Analyser overlays (Google-Flights style): a "typical range" band (p25-p75) behind the
        // line + a dashed average line. Drawn before the data line so they sit behind it.
        const showOverlays = summary && summary.count >= OVERLAY_MIN_POINTS;
        if (showOverlays) {
            const yTop = y(summary.p75), yBot = y(summary.p25);
            svg.appendChild(el('rect', {
                class: 'rg-band', x: padLeft, y: Math.min(yTop, yBot),
                width: Math.max(0, width - PAD.right - padLeft), height: Math.abs(yBot - yTop)
            }));
            const yAvg = y(summary.avg);
            svg.appendChild(el('line', {
                class: 'rg-avg-line', x1: padLeft, y1: yAvg, x2: width - PAD.right, y2: yAvg,
                'stroke-dasharray': '4 4'
            }));
            const at = el('text', { class: 'rg-label rg-avg-text', x: width - PAD.right, y: yAvg - 4, 'text-anchor': 'end' });
            at.textContent = i18n.avg_label || 'avg';
            svg.appendChild(at);
        }

