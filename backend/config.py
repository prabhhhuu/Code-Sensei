import os
from dotenv import load_dotenv

# Always load from backend/.env regardless of cwd
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-fallback")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    HF_TOKEN = os.getenv("HF_TOKEN", "")
