$(document).ready(function() {
    // http://vitalets.github.io/x-editable/docs.html
    $.fn.editable.defaults.mode = "inline";
    $("#failure-reason").editable({
        type: "textarea",
        url: "failure-reason",
        send: "always",
        toggle: "dblclick",
    }).tooltip({  // http://getbootstrap.com/2.3.2/javascript.html#tooltips
        title: "Double-click to edit",
    });
});
