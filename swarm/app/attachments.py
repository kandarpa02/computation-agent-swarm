"""Local-file attachment support for the TUI.

When a user types a line that contains a path to an existing image file,
we read the file, base64-encode it, and attach it to the outgoing message
as an OpenAI-compatible ``image_url`` content part (a ``data:`` URL).

This makes image input work in the CLI exactly the same way it works when
OpenWebUI uploads an image to the HTTP API: both end up as an
``image_url`` content part, which ``messages_to_agent_input`` (in api.py)
converts into an Agents SDK ``input_image`` part that the swarm can see.

Supported image extensions: .png, .jpg, .jpeg, .gif, .webp, .bmp.
Quoted paths (with spaces) are supported. Tokens that don't resolve to an
existing image file are left in the text untouched, so mentioning a path
as plain text still works.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
from pathlib import Path

# Image extensions we inline as data URLs.
_IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
}

# Fallback MIME table for extensions that mimetypes.guess_type may not know
# (e.g. .webp on older Python builds).
_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Tokenizer: double-quoted | single-quoted | bare non-whitespace run.
# We deliberately do NOT use shlex, because shlex(posix=True) eats the
# backslashes in Windows paths (c:\Users\... -> c:Users\...), and
# shlex(posix=False) keeps surrounding quotes verbatim.
_TOKEN_RE = re.compile(r'"[^"]*"|\'[^\']*\'|[^\s]+')


def _tokenize(line: str) -> list[str]:
    """Split a line into tokens, honoring single/double quoted strings."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(line):
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
            tokens.append(raw[1:-1])
        else:
            tokens.append(raw)
    return tokens


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def _read_image_data_url(path: Path) -> str | None:
    """Return a ``data:image/<ext>;base64,...`` URL, or None if not usable."""
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    if not _is_image_path(path):
        return None

    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = _EXT_MIME.get(path.suffix.lower())
    if not mime:
        return None

    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def parse_attachments(line: str) -> tuple[str, list[Path]]:
    """Split a user input line into (clean_text, [image_path, ...]).

    A token is treated as an attachment when it resolves (after tilde
    expansion) to an existing file with a supported image extension.
    Quoted paths are supported. Non-image tokens and tokens that don't
    resolve to a file are left in the text.
    """
    tokens = _tokenize(line)
    text_parts: list[str] = []
    attached: list[Path] = []

    for tok in tokens:
        # Skip obvious URLs — they are not local files and the model can
        # fetch them itself if it has network access.
        if tok.startswith(("http://", "https://", "file://")):
            text_parts.append(tok)
            continue

        try:
            candidate = Path(os.path.expanduser(tok)).expanduser()
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            text_parts.append(tok)
            continue

        if _is_image_path(resolved) and resolved.is_file():
            attached.append(resolved)
        else:
            text_parts.append(tok)

    clean_text = " ".join(text_parts).strip()
    return clean_text, attached


def build_user_message(line: str) -> tuple[dict, list[Path]]:
    """Build an OpenAI-compatible user message dict from a typed line.

    Returns ``(message_dict, attached_paths)`` so the caller can print
    feedback. When no images are attached, the message content is the
    plain string (unchanged from prior behavior). When images are
    attached, content becomes a list of ``text`` and ``image_url`` parts
    — the exact shape OpenWebUI sends.
    """
    clean_text, attached = parse_attachments(line)

    if not attached:
        return {"role": "user", "content": line}, []

    parts: list[dict] = []
    if clean_text:
        parts.append({"type": "text", "text": clean_text})

    for img_path in attached:
        data_url = _read_image_data_url(img_path)
        if data_url is None:
            # Could not read — put the original path back as text so the
            # model at least sees what the user referred to.
            parts.append({"type": "text", "text": str(img_path)})
            continue
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_url, "detail": "auto"},
        })

    return {"role": "user", "content": parts}, attached


def human_size(n: int) -> str:
    """Compact human-readable byte size, e.g. ``12.3 KB``."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"