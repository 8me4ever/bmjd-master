$(function () {
    $("li").click(function () {
        var value = $(this).text();
        if (value != "") {
            window.open(value + "/indexer.html");
        }
    });
});