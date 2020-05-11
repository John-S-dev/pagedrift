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
            
            // Insert the new row after the current one
            currentRow.after(newRow);
            
            // Reindex all rows
            reindexRules();
        });
        
        // Remove row button handler
        $(".removeRuleRow").on("click", function(e) {
            e.preventDefault();
            
            // Only remove if there's more than one row
            if ($("#rulesTable .fieldlist-row").length > 1) {
                $(this).closest(".fieldlist-row").remove();
                reindexRules();
            }
        });
        
        // Verify rule button handler
        $(".verifyRuleRow").on("click", function(e) {
            e.preventDefault();
            
            let row = $(this).closest(".fieldlist-row");
            let field = row.find("select[name$='field']").val();
            let operator = row.find("select[name$='operator']").val();
            let value = row.find("input[name$='value']").val();
            
            // Validate that all fields are filled
            if (!field || field === "None" || !operator || operator === "None" || !value) {
                alert(i18nT('condFillFields', "Please fill in all fields (Field, Operator, and Value) before verifying."));
                return;
            }

            
