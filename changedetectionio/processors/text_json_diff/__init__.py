from loguru import logger

# Processor capabilities
supports_visual_selector = True
supports_browser_steps = True
supports_text_filters_and_triggers = True
supports_text_filters_and_triggers_elements = True
supports_request_type = True



def _task(watch, update_handler):
    from changedetectionio.content_fetchers.exceptions import ReplyWithContentButNoText
    from changedetectionio.processors.text_json_diff.processor import FilterNotFoundInResponse

    text_after_filter = ''

    try:
        # The slow process (we run 2 of these in parallel)
        # Always force reprocess for preview - we want to show the filtered content regardless of checksums
        changed_detected, update_obj, text_after_filter = update_handler.run_changedetection(watch=watch, force_reprocess=True)
    except FilterNotFoundInResponse as e:
        text_after_filter = f"Filter not found in HTML: {str(e)}"
    except ReplyWithContentButNoText as e:
        text_after_filter = "Filter found but no text (empty result)"
    except Exception as e:
        text_after_filter = f"Error: {str(e)}"

    if not text_after_filter.strip():
        text_after_filter = 'Empty content'

    # because run_changedetection always returns bytes due to saving the snapshots etc
    text_after_filter = text_after_filter.decode('utf-8') if isinstance(text_after_filter, bytes) else text_after_filter

    return text_after_filter


