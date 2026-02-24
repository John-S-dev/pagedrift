async (options) => {

    let visualselector_xpath_selectors = options.visualselector_xpath_selectors
    let max_height = options.max_height

    var scroll_y = 0;
    try {
        scroll_y = +document.documentElement.scrollTop || document.body.scrollTop
    } catch (e) {
        console.log(e);
    }

// @todo - if it's SVG or IMG, go into image diff mode

    var size_pos = [];
// after page fetch, inject this JS
// build a map of all elements and their positions (maybe that only include text?)
    var bbox;
    console.log(`Scanning for "${visualselector_xpath_selectors}"`);

    function collectVisibleElements(parent, visibleElements) {
        if (!parent) return; // Base case: if parent is null or undefined, return


        // Add the parent itself to the visible elements array if it's of the specified types
        const tagName = parent.tagName.toLowerCase();
        if (visualselector_xpath_selectors.split(',').includes(tagName)) {
            visibleElements.push(parent);
        }

        // Iterate over the parent's children
        const children = parent.children;
        for (let i = 0; i < children.length; i++) {
            const child = children[i];
            const computedStyle = window.getComputedStyle(child);

            if (
                child.nodeType === Node.ELEMENT_NODE &&
                computedStyle.display !== 'none' &&
                computedStyle.visibility !== 'hidden' &&
                child.offsetWidth >= 0 &&
                child.offsetHeight >= 0 &&
                computedStyle.contentVisibility !== 'hidden'
            ) {
                // If the child is an element and is visible, recursively collect visible elements
                collectVisibleElements(child, visibleElements);
            }
        }
    }

