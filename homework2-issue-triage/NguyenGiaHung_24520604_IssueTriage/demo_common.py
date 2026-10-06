import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_DIR = Path(__file__).parent


def read_settings():
    load_dotenv(PROJECT_DIR / ".env")


def get_model():
    read_settings()
    name = os.getenv("OPENAI_MODEL")
    if not name:
        raise RuntimeError("Thiếu OPENAI_MODEL trong file .env")
    return name


def get_client():
    read_settings()
    key = os.getenv("OPENAI_API_KEY")
    url = os.getenv("OPENAI_BASE_URL")
    if not key or not url:
        raise RuntimeError("Cần khai báo OPENAI_API_KEY và OPENAI_BASE_URL trong file .env")
    return OpenAI(api_key=key, base_url=url)
