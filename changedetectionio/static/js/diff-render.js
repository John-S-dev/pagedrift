$(document).ready(function () {

    // Find all <span> elements inside pre#difference
    var inputs = $('#difference span').toArray();
    inputs.current = 0;

    // Setup visual minimap of difference locations (cells are pre-built in Python)
    var $visualizer = $('#cell-diff-jump-visualiser');
    var $difference = $('#difference');
    var $cells = $visualizer.find('> div');
    var visualizerResolutionCells = $cells.length;
    var cellHeight;

    if ($difference.length && visualizerResolutionCells > 0) {
        var docHeight = $difference[0].scrollHeight;
        cellHeight = docHeight / visualizerResolutionCells;

        // Add click handlers to pre-built cells
        $cells.each(function(i) {
            $(this).data('cellIndex', i);
            $(this).on('click', function() {
                var cellIndex = $(this).data('cellIndex');
                var targetPositionInDifference = cellIndex * cellHeight;
                var viewportHeight = $(window).height();

                // Scroll so target is at viewport center (where eyes expect it)
                window.scrollTo({
                    top: $difference.offset().top + targetPositionInDifference - (viewportHeight / 2),
                    behavior: "smooth"
                });
            });
        });
    }

    $('#jump-next-diff').click(function () {
        if (!inputs || inputs.length === 0) return;

