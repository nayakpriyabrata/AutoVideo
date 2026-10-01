# AutoVideoAI v5.7.8 — Gemini Clip Browser Fallback

v5.7.7 used the Gemini API directly for YouTube clip analysis. A successful API
request therefore opened no browser, while an HTTP 503 moved immediately to the
Groq/local ranker. That behavior was safe but easy to mistake for a silent
Gemini browser failure.

v5.7.8 makes the provider chain explicit:

1. `gemini-hybrid` tries the Gemini API.
2. HTTP 429, 500, 502, 503 and 504 responses retry with 2, 5 and 10 second
   backoff delays.
3. If the API remains unavailable, AutoVideoAI opens the existing signed-in
   Gemini browser profile and asks Gemini to analyse the public YouTube URL.
4. Browser candidates are verified against local speech timing exactly like API
   candidates.
5. Only after API and browser routes fail does Groq/local ranking take over.

Use `gemini-web-hybrid` to open the browser first, or `gemini-api-hybrid` to
disable browser fallback. Gemini browser clip chats support `keep` and
`delete-after-read`; deletion remains conservative and never guesses at an
ambiguous chat menu.
