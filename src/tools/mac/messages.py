"""Send iMessages via the macOS Messages app.

Resolves the recipient (phone number, email, or contact name) and
delegates to Messages.app via AppleScript. Phone numbers should be in
E.164 format (e.g. "+15551234567"). Contact-name lookups require
Contacts.app access permission.
"""

import logging
import re

from livekit.agents import RunContext, function_tool

from tools.mac.utils import (
    applescript_quote,
    is_permission_error,
    macos_only,
    run_osascript,
)

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+?[0-9][0-9\s\-().]{6,}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_MESSAGE_LEN = 2000


def _looks_like_phone(s: str) -> bool:
    return bool(_E164_RE.match(s.strip()))


def _looks_like_email(s: str) -> bool:
    return bool(_EMAIL_RE.match(s.strip()))


def _normalize_phone(s: str) -> str:
    """Strip formatting from a phone-like string. Keeps a leading +."""
    s = s.strip()
    digits = re.sub(r"[\s\-().]", "", s)
    return digits


async def _lookup_contact_handle(name: str) -> tuple[str | None, str | None]:
    """Look up a person in Contacts.app and return (handle, error).

    Returns the first phone number (preferred) or email of a person whose
    full name matches `name`. On no match, returns (None, message).
    """
    name_q = applescript_quote(name)
    script = f'''
tell application "Contacts"
    set matches to (every person whose name is "{name_q}")
    if (count of matches) is 0 then
        set matches to (every person whose name contains "{name_q}")
    end if
    if (count of matches) is 0 then
        return "NONE"
    end if
    set p to item 1 of matches
    set phones to value of phones of p
    if (count of phones) > 0 then
        return "PHONE:" & (item 1 of phones)
    end if
    set emails to value of emails of p
    if (count of emails) > 0 then
        return "EMAIL:" & (item 1 of emails)
    end if
    return "NOHANDLE"
end tell
'''
    rc, out, err = await run_osascript(script, timeout=8.0)
    if rc != 0:
        if is_permission_error(err):
            return None, (
                "Contacts access is denied. Grant it in System Settings → "
                "Privacy & Security → Contacts."
            )
        return None, f"Contacts lookup failed: {err or 'unknown error'}"

    if out == "NONE":
        return None, f"No contact found matching '{name}'."
    if out == "NOHANDLE":
        return None, f"Contact '{name}' has no phone or email."
    if out.startswith("PHONE:"):
        return _normalize_phone(out[len("PHONE:") :]), None
    if out.startswith("EMAIL:"):
        return out[len("EMAIL:") :].strip(), None
    return None, f"Unexpected Contacts response: {out}"


async def _resolve_recipient(recipient: str) -> tuple[str | None, str | None]:
    """Resolve `recipient` to a Messages handle (phone or email).

    Returns (handle, error). If `recipient` already looks like a phone
    number or email, it's returned as-is (phone normalized).
    """
    r = recipient.strip()
    if not r:
        return None, "Recipient is empty."
    if _looks_like_email(r):
        return r, None
    if _looks_like_phone(r):
        return _normalize_phone(r), None
    return await _lookup_contact_handle(r)


@function_tool(
    name="send_imessage",
    description=(
        "Send an iMessage via the macOS Messages app. Use when the user "
        "says 'text [person] [message]', 'send a message to [person] "
        "saying...', or 'iMessage [person]'.\n\n"
        "`recipient` accepts three formats:\n"
        "  - Phone number in E.164 (e.g. '+15551234567') - preferred\n"
        "  - Email address tied to an iMessage account\n"
        "  - Full name of a person in Contacts.app (looked up at send "
        "time; ambiguous names pick the first match)\n\n"
        "`message` is the literal text to send (max 2000 chars). It is "
        "sent verbatim - do not paraphrase the user's wording.\n\n"
        "IMPORTANT: messages are sent immediately and cannot be recalled. "
        "Before calling this tool, repeat the recipient and message back "
        "to the user and get explicit confirmation. Requires Messages and "
        "(for name lookup) Contacts permission."
    ),
)
async def send_imessage(
    context: RunContext, recipient: str, message: str
) -> str:
    if msg := macos_only("iMessage"):
        return msg

    if not message or not message.strip():
        return "Message text is empty - nothing to send."
    if len(message) > _MAX_MESSAGE_LEN:
        return f"Message too long ({len(message)} chars; max {_MAX_MESSAGE_LEN})."

    handle, err = await _resolve_recipient(recipient)
    if handle is None:
        return err or f"Could not resolve recipient '{recipient}'."

    msg_q = applescript_quote(message)
    handle_q = applescript_quote(handle)
    script = f'''
tell application "Messages"
    set targetService to missing value
    repeat with s in services
        if service type of s is iMessage then
            set targetService to s
            exit repeat
        end if
    end repeat
    if targetService is missing value then
        error "No iMessage service is configured. Sign in to Messages first."
    end if
    set targetBuddy to buddy "{handle_q}" of targetService
    send "{msg_q}" to targetBuddy
    return "{handle_q}"
end tell
'''
    rc, out, scripterr = await run_osascript(script, timeout=15.0)
    if rc != 0:
        if is_permission_error(scripterr):
            return (
                "Messages access is denied. Grant Automation permission "
                "for Messages in System Settings → Privacy & Security → "
                "Automation."
            )
        logger.warning("send_imessage failed: %s", scripterr)
        return f"Failed to send iMessage: {scripterr or 'unknown error'}"

    sent_to = out or handle
    return f"Sent iMessage to {sent_to}."


MESSAGES_TOOLS = [send_imessage]
