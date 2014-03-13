$(document).ready(function() {
    // http://vitalets.github.io/x-editable/docs.html
    $.fn.editable.defaults.mode = "inline";
    $("#failure-reason").editable({
        type: "textarea",
        url: "failure-reason",
        send: "always",
        toggle: "dblclick",
        success: function(_, newValue) {
            parent.$("tr.info > td:eq(3) > span").text(truncate(newValue, 30));
        },
    });
    $("#notes").editable({
        type: "textarea",
        url: "notes",
        send: "always",
        toggle: "dblclick",
        success: function(_, newValue) {
            parent.$("tr.info > td:eq(4)").text(truncate(newValue, 30));
        },
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
                    parent.$('tr.info').remove();
                });
        }
        return false;
    });
    $("#permalink").after(del);
});

function truncate(str, len) {
    return str.length > len ? str.substr(0, len) + "..." : str;
}
