"""Shared host media budget adapter for the parser module."""

from contextlib import nullcontext


def host_media_context(context):
    """Return the Zhiban media budget context, or a no-op context."""
    scheduler = getattr(getattr(context, "zhiban_parent", None), "scheduler", None)
    if scheduler is None or not hasattr(scheduler, "media"):
        return nullcontext()
    return scheduler.media()
