import os

import requests
import urllib3
from dotenv import load_dotenv

load_dotenv(interpolate=False, override=True)

# Suppress warnings while testing against self-signed local controller certs.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = (os.getenv("unifi_url") or "").rstrip("/")
username = os.getenv("unifi_username") or os.getenv("username")
password = os.getenv("unifi_password") or os.getenv("password")


auth = requests.post(
    f"{base_url}/api/auth/login",
    headers={"Content-Type": "application/json"},
    json={
        "username": username,
        "password": password,
    },
    verify=False,
    timeout=15,
)

print(f"Status: {auth.status_code}")
print(auth.text)
cookies = auth.cookies.get_dict()
print(f"Cookies returned: {auth.cookies.get_dict()}")