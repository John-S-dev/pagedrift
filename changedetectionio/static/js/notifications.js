function checkDiscordHtmlWarning() {
    var urls = $('textarea.notification-urls').val() || '';
    var format = $('select.notification-format').val() || '';
    var isDiscord = /discord:\/\/|https:\/\/discord(?:app)?\.com\/api/i.test(urls);
    var isHtml = format === 'html' || format === 'htmlcolor';
    if (isDiscord && isHtml) {
        $('#discord-html-format-warning').show();
    } else {
        $('#discord-html-format-warning').hide();
    }
}

