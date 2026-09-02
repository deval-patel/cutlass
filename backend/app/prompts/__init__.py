"""Prompt harness (Plan 2): versioned template files + a builder.

Prompts live in templates/<version>/*.md so changes are reviewable diffs
and every generated draft can record which prompt version produced it.
Templates use string.Template ($placeholder) because the prompts embed
JSON examples with literal braces.
"""
