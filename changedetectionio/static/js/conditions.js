$(document).ready(function () {
    // Function to set up button event handlers
    function setupButtonHandlers() {
        // Unbind existing handlers first to prevent duplicates
        $(".addRuleRow, .removeRuleRow, .verifyRuleRow").off("click");
        
        // Add row button handler
        $(".addRuleRow").on("click", function(e) {
            e.preventDefault();
            
            let currentRow = $(this).closest(".fieldlist-row");
            
            // Clone without events
            let newRow = currentRow.clone(false);
            
            // Reset input values in the cloned row
            newRow.find("input").val("");
            newRow.find("select").prop("selectedIndex", 0);
            
