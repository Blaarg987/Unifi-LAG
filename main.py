import os
import json
import requests
import urllib3
from dotenv import load_dotenv
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = os.getenv("unifi_url")
username = os.getenv("unifi_username")
password = os.getenv("unifi_password")


def get_cookie():
    auth = requests.post(
        f"{base_url}/api/auth/login",
        headers={"Content-Type": "application/json"},
        json={"username": username, "password": password},
        verify=False,
        timeout=15,
    )

    if auth.status_code == 200:
        print("Authenticated with UniFi controller.")
        return auth.cookies
    else:
        print(f"Authentication failed. Status code: {auth.status_code}")
        raise KeyError("Check your credentials and try again.")


cookies = get_cookie()

lacp_response = requests.get(
    f"{base_url}/proxy/network/api/s/default/stat/device",
    headers={"Content-Type": "application/json"},
    cookies=cookies,
    verify=False,
    timeout=15,
)

lacp_json = lacp_response.json()

for device in lacp_json["data"]:
    if device["type"] != "usw":
        continue
    for port in device["port_table"]:
        if port["op_mode"] != "aggregate":
           continue
        for member in port["lacp_state"]:
           print(member["member_port"], member["active"])
            