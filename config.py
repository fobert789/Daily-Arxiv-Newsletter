import os
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/newsletter/.env")

MODELS = [
    "x-ai/grok-4.1-fast",
    "deepseek/deepseek-v3.2",
    "minimax/minimax-m2.5",
    "z-ai/glm-4.5-air",
    "openrouter/auto",   # last resort: OpenRouter picks
]
MY_EMAIL           = os.getenv("MY_EMAIL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ARXIV_PAGE_SIZE    = 10
ARXIV_DELAY        = 5
TITLE_SCREEN_KEEP  = 15   # candidates passed from title screen to abstract screen
