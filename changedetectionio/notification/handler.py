
import time
import re
from loguru import logger
from urllib.parse import urlparse
from .email_helpers import as_monospaced_html_email
from ..diff import HTML_REMOVED_STYLE, REMOVED_PLACEMARKER_OPEN, REMOVED_PLACEMARKER_CLOSED, ADDED_PLACEMARKER_OPEN, HTML_ADDED_STYLE, \
    ADDED_PLACEMARKER_CLOSED, CHANGED_INTO_PLACEMARKER_OPEN, CHANGED_INTO_PLACEMARKER_CLOSED, CHANGED_PLACEMARKER_OPEN, \
    CHANGED_PLACEMARKER_CLOSED, HTML_CHANGED_STYLE, HTML_CHANGED_INTO_STYLE
import re

from ..notification_service import NotificationContextData, add_rendered_diff_to_notification_vars

newline_re = re.compile(r'\r\n|\r|\n')

def markup_text_links_to_html(body):
    """
    Convert plaintext to HTML with clickable links.
    Uses Jinja2's escape and Markup for XSS safety.
    """
    from linkify_it import LinkifyIt
    from markupsafe import Markup, escape

    linkify = LinkifyIt()

    # Match URLs in the ORIGINAL text (before escaping)
    matches = linkify.match(body)

    if not matches:
        # No URLs, just escape everything
        return Markup(escape(body))

    result = []
    last_index = 0

    # Process each URL match
    for match in matches:
        # Add escaped text before the URL
        if match.index > last_index:
            text_part = body[last_index:match.index]
            result.append(escape(text_part))

        # Add the link with escaped URL (both in href and display)
        url = match.url
        result.append(Markup(f'<a href="{escape(url)}">{escape(url)}</a>'))

        last_index = match.last_index

    # Add remaining escaped text
    if last_index < len(body):
        result.append(escape(body[last_index:]))

    # Join all parts
    return str(Markup(''.join(str(part) for part in result)))

def notification_format_align_with_apprise(n_format : str):
    """
    Correctly align changedetection's formats with apprise's formats
    Probably these are the same - but good to be sure.
    These set the expected OUTPUT format type
    :param n_format:
    :return:
    """
    from apprise import NotifyFormat

    if not n_format:
        return NotifyFormat.TEXT.value

    if n_format.startswith('html'):
        # Apprise only knows 'html' not 'htmlcolor' etc, which shouldnt matter here
        n_format = NotifyFormat.HTML.value
    elif n_format.startswith('markdown'):
        # probably the same but just to be safe
        n_format = NotifyFormat.MARKDOWN.value
    elif n_format.startswith('text'):
        # probably the same but just to be safe
        n_format = NotifyFormat.TEXT.value
    else:
        n_format = NotifyFormat.TEXT.value

    return n_format


def apply_html_color_to_body(n_body: str):
    # https://github.com/dgtlmoon/changedetection.io/issues/821#issuecomment-1241837050
    n_body = n_body.replace(REMOVED_PLACEMARKER_OPEN,
                            f'<span style="{HTML_REMOVED_STYLE}" role="deletion" aria-label="Removed text" title="Removed text">')
    n_body = n_body.replace(REMOVED_PLACEMARKER_CLOSED, f'</span>')
    n_body = n_body.replace(ADDED_PLACEMARKER_OPEN,
                            f'<span style="{HTML_ADDED_STYLE}" role="insertion" aria-label="Added text" title="Added text">')
    n_body = n_body.replace(ADDED_PLACEMARKER_CLOSED, f'</span>')
    # Handle changed/replaced lines (old → new)
    n_body = n_body.replace(CHANGED_PLACEMARKER_OPEN,
                            f'<span style="{HTML_CHANGED_STYLE}" role="note" aria-label="Changed text" title="Changed text">')
    n_body = n_body.replace(CHANGED_PLACEMARKER_CLOSED, f'</span>')
    n_body = n_body.replace(CHANGED_INTO_PLACEMARKER_OPEN,
                            f'<span style="{HTML_CHANGED_INTO_STYLE}" role="note" aria-label="Changed into" title="Changed into">')
    n_body = n_body.replace(CHANGED_INTO_PLACEMARKER_CLOSED, f'</span>')
    return n_body

def apply_discord_markdown_to_body(n_body):
    """
    Discord does not support <del> but it supports non-standard ~~strikethrough~~
    :param n_body:
    :return:
    """
    import re
    # Define the mapping between your placeholders and markdown markers
    replacements = [
        (REMOVED_PLACEMARKER_OPEN, '~~', REMOVED_PLACEMARKER_CLOSED, '~~'),
        (ADDED_PLACEMARKER_OPEN, '**', ADDED_PLACEMARKER_CLOSED, '**'),
        (CHANGED_PLACEMARKER_OPEN, '~~', CHANGED_PLACEMARKER_CLOSED, '~~'),
        (CHANGED_INTO_PLACEMARKER_OPEN, '**', CHANGED_INTO_PLACEMARKER_CLOSED, '**'),
    ]
    # So that the markdown gets added without any whitespace following it which would break it
    for open_tag, open_md, close_tag, close_md in replacements:
        # Regex: match opening tag, optional whitespace, capture the content, optional whitespace, then closing tag
        pattern = re.compile(
            re.escape(open_tag) + r'(\s*)(.*?)?(\s*)' + re.escape(close_tag),
            flags=re.DOTALL
        )
        n_body = pattern.sub(lambda m: f"{m.group(1)}{open_md}{m.group(2)}{close_md}{m.group(3)}", n_body)
    return n_body

def apply_standard_markdown_to_body(n_body):
    """
    Apprise does not support ~~strikethrough~~ but it will convert <del> to HTML strikethrough.
    :param n_body:
    :return:
    """
    import re
    # Define the mapping between your placeholders and markdown markers
    replacements = [
        (REMOVED_PLACEMARKER_OPEN, '<del>', REMOVED_PLACEMARKER_CLOSED, '</del>'),
        (ADDED_PLACEMARKER_OPEN, '**', ADDED_PLACEMARKER_CLOSED, '**'),
        (CHANGED_PLACEMARKER_OPEN, '<del>', CHANGED_PLACEMARKER_CLOSED, '</del>'),
        (CHANGED_INTO_PLACEMARKER_OPEN, '**', CHANGED_INTO_PLACEMARKER_CLOSED, '**'),
    ]

    # So that the markdown gets added without any whitespace following it which would break it
    for open_tag, open_md, close_tag, close_md in replacements:
        # Regex: match opening tag, optional whitespace, capture the content, optional whitespace, then closing tag
        pattern = re.compile(
            re.escape(open_tag) + r'(\s*)(.*?)?(\s*)' + re.escape(close_tag),
            flags=re.DOTALL
        )
        n_body = pattern.sub(lambda m: f"{m.group(1)}{open_md}{m.group(2)}{close_md}{m.group(3)}", n_body)
    return n_body


def replace_placemarkers_in_text(text, url, requested_output_format):
    """
    Replace diff placemarkers in text based on the URL service type and requested output format.
    Used for both notification title and body to ensure consistent placeholder replacement.

    :param text: The text to process
    :param url: The notification URL (to detect service type)
    :param requested_output_format: The output format (html, htmlcolor, markdown, text, etc.)
    :return: Processed text with placemarkers replaced
    """
    if not text:
        return text

    if url.startswith('tgram://'):
        # Telegram only supports a limited subset of HTML
        # Use strikethrough for removed content, bold for added content
        text = text.replace(REMOVED_PLACEMARKER_OPEN, '<s>')
        text = text.replace(REMOVED_PLACEMARKER_CLOSED, '</s>')
        text = text.replace(ADDED_PLACEMARKER_OPEN, '<b>')
        text = text.replace(ADDED_PLACEMARKER_CLOSED, '</b>')
        # Handle changed/replaced lines (old → new)
        text = text.replace(CHANGED_PLACEMARKER_OPEN, '<s>')
        text = text.replace(CHANGED_PLACEMARKER_CLOSED, '</s>')
        text = text.replace(CHANGED_INTO_PLACEMARKER_OPEN, '<b>')
        text = text.replace(CHANGED_INTO_PLACEMARKER_CLOSED, '</b>')
    elif (url.startswith('discord://') or url.startswith('https://discordapp.com/api/webhooks')
          or url.startswith('https://discord.com/api')) and requested_output_format == 'html':
        # Discord doesn't support HTML, use Discord markdown
        text = apply_discord_markdown_to_body(n_body=text)
    elif requested_output_format == 'htmlcolor':
        # https://github.com/dgtlmoon/changedetection.io/issues/821#issuecomment-1241837050
        text = text.replace(REMOVED_PLACEMARKER_OPEN, f'<span style="{HTML_REMOVED_STYLE}" role="deletion" aria-label="Removed text" title="Removed text">')
        text = text.replace(REMOVED_PLACEMARKER_CLOSED, f'</span>')
        text = text.replace(ADDED_PLACEMARKER_OPEN, f'<span style="{HTML_ADDED_STYLE}" role="insertion" aria-label="Added text" title="Added text">')
        text = text.replace(ADDED_PLACEMARKER_CLOSED, f'</span>')
        # Handle changed/replaced lines (old → new)
        text = text.replace(CHANGED_PLACEMARKER_OPEN, f'<span style="{HTML_CHANGED_STYLE}" role="note" aria-label="Changed text" title="Changed text">')
        text = text.replace(CHANGED_PLACEMARKER_CLOSED, f'</span>')
        text = text.replace(CHANGED_INTO_PLACEMARKER_OPEN, f'<span style="{HTML_CHANGED_INTO_STYLE}" role="note" aria-label="Changed into" title="Changed into">')
        text = text.replace(CHANGED_INTO_PLACEMARKER_CLOSED, f'</span>')
    elif requested_output_format == 'markdown':
        # Markdown to HTML - Apprise will convert this to HTML
        text = apply_standard_markdown_to_body(n_body=text)
    else:
        # plaintext, html, and default - use simple text markers
        text = text.replace(REMOVED_PLACEMARKER_OPEN, '(removed) ')
        text = text.replace(REMOVED_PLACEMARKER_CLOSED, '')
        text = text.replace(ADDED_PLACEMARKER_OPEN, '(added) ')
        text = text.replace(ADDED_PLACEMARKER_CLOSED, '')
        text = text.replace(CHANGED_PLACEMARKER_OPEN, f'(changed) ')
        text = text.replace(CHANGED_PLACEMARKER_CLOSED, f'')
        text = text.replace(CHANGED_INTO_PLACEMARKER_OPEN, f'(into) ')
        text = text.replace(CHANGED_INTO_PLACEMARKER_CLOSED, f'')

    return text

def process_notification(n_object: NotificationContextData, datastore):
    import apprise
    from apprise import NotifyFormat
    from .apprise_plugin.assets import apprise_asset
    from changedetectionio.jinja2_custom import render as jinja_render
    from . import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH, default_notification_format, valid_notification_formats
    # be sure its registered
    from .apprise_plugin.custom_handlers import apprise_http_custom_handler
    # Register custom Discord plugin
    from .apprise_plugin.discord import NotifyDiscordCustom

    if not isinstance(n_object, NotificationContextData):
        raise TypeError(f"Expected NotificationContextData, got {type(n_object)}")

    now = time.time()
    if n_object.get('notification_timestamp'):
        logger.trace(f"Time since queued {now-n_object['notification_timestamp']:.3f}s")

    # Insert variables into the notification content
    notification_parameters = create_notification_parameters(n_object, datastore)

    requested_output_format = n_object.get('notification_format', default_notification_format)
    logger.debug(f"Requested notification output format: '{requested_output_format}'")

    # If we arrived with 'System default' then look it up
    if requested_output_format == USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH:
        # Initially text or whatever
        requested_output_format = datastore.data['settings']['application'].get('notification_format', default_notification_format)

    requested_output_format_original = requested_output_format

    # Now clean it up so it fits perfectly with apprise
    requested_output_format = notification_format_align_with_apprise(n_format=requested_output_format)

    logger.trace(f"Complete notification body including Jinja and placeholders calculated in  {time.time() - now:.2f}s")

    # https://github.com/caronc/apprise/wiki/Development_LogCapture
    # Anything higher than or equal to WARNING (which covers things like Connection errors)
    # raise it as an exception

    sent_objs = []

    if 'as_async' in n_object:
        apprise_asset.async_mode = n_object.get('as_async')

    apobj = apprise.Apprise(debug=True, asset=apprise_asset)

    # Override Apprise's built-in Discord plugin with our custom one
    # This allows us to use colored embeds for diff content
    # First remove the built-in discord plugin, then add our custom one
    apprise.plugins.N_MGR.remove('discord')
    apprise.plugins.N_MGR.add(NotifyDiscordCustom, schemas='discord')

    if not n_object.get('notification_urls'):
        return None

    n_object.update(add_rendered_diff_to_notification_vars(
        notification_scan_text=n_object.get('notification_body', '')+n_object.get('notification_title', ''),
        current_snapshot=n_object.get('current_snapshot'),
        prev_snapshot=n_object.get('prev_snapshot'),
        # Should always be false for 'text' mode or its too hard to read
        # But otherwise, this could be some setting
        word_diff=False if requested_output_format_original == 'text' else True,
        # HTML-format notifications must escape diff content (GHSA-q8xq-qg4x-wphg).
        # FormattableDiff/Extract escape internally so {{ diff(...) }} stays callable —
        # the post-Jinja escape loop below would otherwise convert them to plain str.
        escape_output='html' in requested_output_format,
        )
    )

    # {{ raw_diff }} always holds the actual diff regardless of AI Change Summary
    n_object['raw_diff'] = n_object.get('diff', '')

    # AI Change Summary: optionally replace {{ diff }} with the AI summary
    _llm_change_summary = (n_object.get('_llm_change_summary') or '').strip()
    from changedetectionio.llm.evaluator import get_llm_settings
    _override_diff = get_llm_settings(datastore).override_diff_with_summary
    if _llm_change_summary and _override_diff:
        n_object['diff'] = _llm_change_summary

    # Lazily populate llm_summary / llm_intent if used in notification template
    scan_text = n_object.get('notification_body', '') + n_object.get('notification_title', '')
    if 'llm_summary' in scan_text or 'llm_intent' in scan_text or 'raw_diff' in scan_text:
        n_object['llm_summary'] = _llm_change_summary or (n_object.get('_llm_result') or {}).get('summary', '')
        n_object['llm_intent'] = n_object.get('_llm_intent', '')

    # Escape diff/snapshot variables before Jinja renders them into an HTML notification.
    # GHSA-q8xq-qg4x-wphg: inscriptis decodes HTML entities when converting text/html
    # pages to snapshot text, so a page that visibly displays "&lt;a href...&gt;" yields
    # literal "<a href...>" in the snapshot — which would otherwise render as live
    # markup in HTML emails / Telegram (parse_mode=html) / Discord embeds, letting a
    # watched page inject phishing links into the operator's notification channel.
    # Also covers #3529 — raw '<' chars from text/plain pages breaking HTML email layout.
    # The operator's own template HTML (e.g. <a href="{{watch_url}}">) is outside the
    # variable values so it stays untouched. Diff placemarkers contain no HTML chars,
    # so they survive escape and are still replaced with <span> tags later.
    if 'html' in requested_output_format:
        from markupsafe import escape as html_escape
        from changedetectionio.notification_service import FormattableDiff, FormattableExtract
        _page_content_keys = {'raw_diff', 'current_snapshot', 'prev_snapshot', 'triggered_text'}
        for key in [k for k in notification_parameters if k.startswith('diff') or k in _page_content_keys]:
            value = notification_parameters.get(key)
            if not value:
                continue
            # FormattableDiff / FormattableExtract are callable str subclasses — {{ diff(lines=5) }}
            # etc. relies on __call__. Wrapping them with str(html_escape(...)) here would lose
            # __call__ and break those tokens. They escape internally via escape_output=True
            # (set by add_rendered_diff_to_notification_vars above) for both __str__ and __call__.
            if isinstance(value, (FormattableDiff, FormattableExtract)):
                continue
            notification_parameters[key] = str(html_escape(str(value)))

    with (apprise.LogCapture(level=apprise.logging.DEBUG) as logs):
        for url in n_object['notification_urls']:

            n_body = jinja_render(template_str=n_object.get('notification_body', ''), **notification_parameters)
            n_title = jinja_render(template_str=n_object.get('notification_title', ''), **notification_parameters)

            if n_object.get('markup_text_links_to_html_links'):
                n_body = markup_text_links_to_html(body=n_body)

            url = url.strip()
            if not url or url.startswith('#'):
                logger.debug(f"Skipping commented out or empty notification URL - '{url}'")
                continue

            logger.info(f">> Process Notification: AppRise start notifying '{url}'")
            url = jinja_render(template_str=url, **notification_parameters)

            if 'html' in requested_output_format:
                # Since the n_body is always some kind of text from the 'diff' engine, attempt to preserve whitespaces that get sent to the HTML output
                # But only where its more than 1 consecutive whitespace, otherwise "and this" becomes "and&nbsp;this" etc which is too much.
                n_body = n_body.replace('  ', '&nbsp;&nbsp;')

            (url, n_body, n_title) = apply_service_tweaks(url=url, n_body=n_body, n_title=n_title, requested_output_format=requested_output_format_original)

            apprise_input_format = "NO-THANKS-WE-WILL-MANAGE-ALL-OF-THIS"

            if not 'format=' in url:
                parsed_url = urlparse(url)
                prefix_add_to_url = '?' if not parsed_url.query else '&'

                # THIS IS THE TRICK HOW TO DISABLE APPRISE DOING WEIRD AUTO-CONVERSION WITH BREAKING BR TAGS ETC
                if 'html' in requested_output_format:
                    url = f"{url}{prefix_add_to_url}format={NotifyFormat.HTML.value}"
                    apprise_input_format = NotifyFormat.HTML.value
                elif 'text' in requested_output_format:
                    url = f"{url}{prefix_add_to_url}format={NotifyFormat.TEXT.value}"
                    apprise_input_format = NotifyFormat.TEXT.value

                elif requested_output_format == NotifyFormat.MARKDOWN.value:
                    # Convert markdown to HTML ourselves since not all plugins do this
                    from apprise.conversion import markdown_to_html
                    # Make sure there are paragraph breaks around horizontal rules
                    n_body = n_body.replace('---', '\n\n---\n\n')
                    n_body = markdown_to_html(n_body)
                    url = f"{url}{prefix_add_to_url}format={NotifyFormat.HTML.value}"
                    requested_output_format = NotifyFormat.HTML.value
                    apprise_input_format = NotifyFormat.HTML.value  # Changed from MARKDOWN to HTML

            else:
                # ?format was IN the apprise URL, they are kind of on their own here, we will try our best
                if 'format=html' in url:
                    n_body = newline_re.sub('<br>\r\n', n_body)
                    # This will also prevent apprise from doing conversion
                    apprise_input_format = NotifyFormat.HTML.value
                    requested_output_format = NotifyFormat.HTML.value
                elif 'format=text' in url:
                    apprise_input_format = NotifyFormat.TEXT.value
                    requested_output_format = NotifyFormat.TEXT.value

