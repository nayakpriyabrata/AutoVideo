# AutoVideoAI v5.7.6 — Gemini Web Capture and Cleanup

This maintenance release fixes a Gemini Web failure where a short, stable
"thinking" or status element could be captured instead of the completed JSON
answer. AutoVideoAI now waits for a complete JSON-object-shaped response,
checks that generation has stopped, and selects the longest complete response
block when Gemini renders nested copies of the same answer.

`gemini_chat_cleanup: delete-after-read` now applies to every submitted
temporary chat. Cleanup runs after successful capture and also after an answer
timeout or extraction failure. Cleanup remains conservative: if the visible
current-chat menu and Delete confirmation cannot be identified unambiguously,
the chat is left in place and the runtime log explains that outcome.

Expected runtime messages are:

```text
[Gemini] Temporary chat cleanup armed for this submitted chat.
[Gemini] Temporary chat cleanup: deleted.
```

or, after a Gemini UI change:

```text
[Gemini] Temporary chat cleanup: not deleted; an unambiguous current-chat Delete control was not found.
```

Existing jobs and configuration files remain compatible.
