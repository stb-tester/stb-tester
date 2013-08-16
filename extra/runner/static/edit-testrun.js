$(document).ready(function() {
    // http://vitalets.github.io/x-editable/docs.html
    $.fn.editable.defaults.mode = "inline";
    $("#failure-reason").editable({
        type: "textarea",
        url: "failure-reason",
        send: "always",
        toggle: "dblclick",
    });
    $("#notes").editable({
        type: "textarea",
        url: "notes",
        send: "always",
        toggle: "dblclick",
    });
    // http://getbootstrap.com/2.3.2/javascript.html#tooltips
    $("#failure-reason, #notes").tooltip({
        title: "Double-click to edit",
    });

    var del = $(
        "<a id='delete' class='text-error' href='#'>[Hide this result]</a>");
    del.on("click", function() {
        if (confirm("Are you sure?")) {
            $.post(
                "delete",
                function() {
                    del.replaceWith(
                        "<span id='deleted' class='text-error'>(Deleted)</span>");
                });
        }
        return false;
    });
    $("#permalink").after(del);
});
