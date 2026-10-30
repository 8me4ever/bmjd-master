$(function () {
    $('span').tooltipsy({
        offset: [10, 0],
        content: '',
        css: {
            'padding': '10px',
            'max-width': '600px',
            'color': '#303030',
            'background-color': '#f5f5b5',
            'border': '1px solid #deca7e',
            '-moz-box-shadow': '0 0 10px rgba(0, 0, 0, .5)',
            '-webkit-box-shadow': '0 0 10px rgba(0, 0, 0, .5)',
            'box-shadow': '0 0 10px rgba(0, 0, 0, .5)',
            'text-shadow': 'none'
        }
    });
    var hash = decodeURIComponent(window.location.search);
    var newHash = hash.replace("?", "");
    $("a[name='" + newHash + "']").parent().css({ "background": "#0065db" });
    $("a[name='" + newHash + "']").css({ "color": "#FFF" });
    $("a[name='" + newHash + "']").parent().next().css("border", "solid 1px rgb(0, 101, 219)")
    window.scrollTo(0, $("a[name='" + newHash + "']").offset().top - 50);
    $('a').click(function () {
        history.back(-1);
    });
});