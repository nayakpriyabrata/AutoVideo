"""Read-only model discovery: python3 -m engine.providers.gemini_models.

Uses the documented Models API; keys are sent as headers and never printed.
Discovery is not a guarantee of model availability or YouTube-video support.
"""
import os
import requests


def available_models(key):
    models, token = [], None
    for _ in range(20):
        params = {"pageSize": 1000}
        if token:
            params["pageToken"] = token
        response = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                                headers={"x-goog-api-key": key}, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        models.extend(m["name"].removeprefix("models/") for m in data.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))
        token = data.get("nextPageToken")
        if not token:
            return sorted(set(models))
    raise RuntimeError("Model listing pagination exceeded safety limit")


def main():
    from ..env_config import load_environment
    load_environment()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY is missing. Run python3 cli.py v3 env-doctor.")
    try:
        models = available_models(key)
    except requests.RequestException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        raise SystemExit(f"Gemini model discovery unavailable (HTTP {code or 'network error'}); no generation was submitted.")
    print("Models advertising generateContent (confirm video support before choosing):")
    print("\n".join(models))


if __name__ == "__main__":
    main()
