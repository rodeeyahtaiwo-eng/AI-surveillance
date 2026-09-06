import os

from dotenv import load_dotenv

load_dotenv()

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://localhost:8000")
SAMPLE_FPS = float(os.environ.get("SAMPLE_FPS", "2"))
