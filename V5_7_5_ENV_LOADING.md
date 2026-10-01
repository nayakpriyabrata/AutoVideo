# AutoVideoAI v5.7.5 — Environment Loading

v5.7.5 makes API-key discovery deterministic across CLI, Streamlit, WSL and
launchers.

- The application-directory .env is loaded even when the process starts from a
  different working directory.
- .env.local, the parent Auto folder, the shared user configuration, and recent
  AutoVideoAI version folders are checked for missing values.
- Empty exported shell variables no longer block a non-empty .env value.
- UTF-8 BOM files are supported.
- GOOGLE_API_KEY is accepted as an alias for GEMINI_API_KEY.
- Common Groq, ElevenLabs and FAL aliases are normalized.
- Run python3 cli.py v3 env-doctor to see detected variable names and source
  files without revealing any secret values.
