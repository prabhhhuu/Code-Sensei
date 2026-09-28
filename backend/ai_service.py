import os
import requests
from dotenv import load_dotenv

# Always load .env from the backend folder
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Model IDs must exist on your Groq plan — check https://console.groq.com/docs/models
# llama-3.3-70b-versatile was moved to Enterprise-only on Aug 16, 2026.
MODELS = {
    "gpt-oss-120b": {"name": "openai/gpt-oss-120b",  "display": "GPT-OSS 120B (Best)"},
    "gpt-oss-20b":  {"name": "openai/gpt-oss-20b",   "display": "GPT-OSS 20B (Fastest)"},
}

MODE_PROMPTS = {
    "explain":  "You are a code explanation assistant. Analyze the provided code and explain what it does in a clear, beginner-friendly way. Break down each part and explain the logic. Use markdown formatting with headers and bullet points.",
    "improve":  "You are a code improvement assistant. Analyze the provided code and suggest specific improvements for readability, best practices, maintainability, and error handling. Provide improved code examples with markdown formatting.",
    "optimize": "You are a code optimization assistant. Analyze the provided code and suggest performance improvements including time complexity, space complexity, and algorithmic improvements. Provide optimized code examples with markdown formatting.",
    "security": "You are a code security analyst. Analyze the provided code for security vulnerabilities, common attack vectors, and input validation issues. Provide fixed code with markdown formatting.",
}


def get_ai_response(code: str, language: str, mode: str, model: str = "gpt-oss-120b") -> str:
    """Get AI response from Groq API."""
    if not GROQ_API_KEY:
        return "❌ Error: GROQ_API_KEY not set in .env file."

    model_info  = MODELS.get(model, MODELS["gpt-oss-120b"])
    model_name  = model_info["name"]
    mode_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["explain"])

    user_message = f"""Please {mode} this {language} code:

```{language}
{code}
```

Provide a detailed analysis with clear explanations and proper markdown formatting."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    model_name,
        "messages": [
            {"role": "system", "content": mode_prompt},
            {"role": "user",   "content": user_message}
        ],
        "max_tokens":  2048,
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=90
        )
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0].get("message", {}).get("content", "No response generated.").strip()
            return "Unexpected response format from AI."
        elif response.status_code == 401:
            return "❌ Invalid Groq API key. Update GROQ_API_KEY in your .env file."
        elif response.status_code == 404:
            return "❌ Model not available on your Groq plan — it may have been retired. Update model IDs in ai_service.py (see https://console.groq.com/docs/models)."
        elif response.status_code == 429:
            return "⏳ Rate limit reached. Please wait a few seconds and try again."
        else:
            return f"❌ API error {response.status_code}: {response.text[:300]}"

    except requests.exceptions.Timeout:
        return "⏳ Request timed out. Please try again."
    except Exception as e:
        return f"❌ Error: {str(e)}"


def get_available_models() -> dict:
    return MODELS
