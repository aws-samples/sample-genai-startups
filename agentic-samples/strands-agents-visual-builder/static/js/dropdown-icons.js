$(document).ready(function() {
    // Initialize the custom dropdown with icons
    initializeDropdownWithIcons();
    
    function initializeDropdownWithIcons() {
        const select = $('#workflow-select');
        
        // Create a wrapper div for our custom dropdown
        select.wrap('<div class="custom-select-wrapper"></div>');
        const wrapper = select.parent();
        
        // Create the custom dropdown elements
        const customSelect = $('<div class="custom-select"></div>');
        const selectedOption = $('<div class="selected-option"></div>');
        const optionsList = $('<div class="options-list"></div>');
        
        // Add the elements to the DOM
        customSelect.append(selectedOption);
        customSelect.append(optionsList);
        wrapper.append(customSelect);
        
        // Hide the original select
        select.css('display', 'none');
        
        // Set the initial selected option text
        updateSelectedOption();
        
        // Populate the options list
        populateOptionsList();
        
        // Toggle dropdown on click
        selectedOption.on('click', function(e) {
            e.stopPropagation();
            customSelect.toggleClass('open');
        });
        
        // Close dropdown when clicking outside
        $(document).on('click', function() {
            customSelect.removeClass('open');
        });
        
        // Handle option selection
        optionsList.on('click', '.option', function() {
            const value = $(this).data('value');
            select.val(value).trigger('change');
            updateSelectedOption();
            customSelect.removeClass('open');
        });
        
        // Update the custom dropdown when the original select changes
        select.on('change', function() {
            updateSelectedOption();
            populateOptionsList();
        });
        
        function updateSelectedOption() {
            const selectedValue = select.val();
            // Clean the text to remove any HTML tags that might be in the option
            const selectedText = select.find('option:selected').text().replace(/<\/?[^>]+(>|$)/g, "").trim();
            const selectedType = select.find('option:selected').data('type');
            
            let icon = '';
            if (selectedValue) {
                icon = selectedType === 'workflow' ? 
                    '<i class="fas fa-diagram-project me-2"></i>' : 
                    '<i class="fas fa-robot me-2"></i>';
            }
            
            selectedOption.html(icon + selectedText);
        }
        
        function populateOptionsList() {
            optionsList.empty();
            
            // Add all options from the original select
            select.find('option').each(function() {
                const value = $(this).val();
                // Clean the text to remove any HTML tags that might be in the option
                const text = $(this).text().replace(/<\/?[^>]+(>|$)/g, "").trim();
                const type = $(this).data('type');
                
                let icon = '';
                if (value) {
                    icon = type === 'workflow' ? 
                        '<i class="fas fa-diagram-project me-2"></i>' : 
                        '<i class="fas fa-robot me-2"></i>';
                }
                
                const option = $(`<div class="option" data-value="${value}">${icon}${text}</div>`);
                
                // Mark as selected if it's the current value
                if (value === select.val()) {
                    option.addClass('selected');
                }
                
            
                
                option.attr('data-type', type || '');
                optionsList.append(option);
            });
        }
    }
});
