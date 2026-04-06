import os
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/newsletter/.env")

PRIMARY_MODEL      = "x-ai/grok-4.1-fast"
FALLBACK_MODEL     = "deepseek/deepseek-v3.2"
MY_EMAIL           = os.getenv("MY_EMAIL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ARXIV_PAGE_SIZE    = 10
ARXIV_DELAY        = 5
PICKER_BATCH_SIZE  = 10
