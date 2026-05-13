from dotenv import load_dotenv
load_dotenv()

import os

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL")

