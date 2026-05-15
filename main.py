import os
from dotenv import load_dotenv
import requests 



load_dotenv()

api_key = os.getenv("UNIFI_API_KEY")
if not api_key:
    raise ValueError("UNIFI_API_KEY is not set in the environment variables.")
host = os.getenv("UNIFI_HOST")

