import os
import requests
import urllib3

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Environment variables for UniFi controller and Proxmox API access
unifi_url = os.getenv("unifi_url")
unifi_username = os.getenv("unifi_username")
unifi_password = os.getenv("unifi_password")
proxmox_auth = os.getenv("proxmox_auth")
proxmox_url = os.getenv("proxmox_url")


# Authenticate with the UniFi controller and return session cookies
def get_unifi_cookie():
    response = requests.post(
        f"{unifi_url}/api/auth/login",
        headers={"Content-Type": "application/json"},
        json={"username": unifi_username, "password": unifi_password},
        verify=False,
        timeout=15,
    )

    if response.status_code == 200:
        print("Authenticated with UniFi controller.")
        return response.cookies
    else:
        print(f"Authentication failed. Status code: {response.status_code}")
        raise KeyError("Check your UniFi credentials and try again.")


# Fetch all device data from the UniFi controller
def get_unifi_devices(cookies):
    response = requests.get(
        f"{unifi_url}/proxy/network/api/s/default/stat/device",
        headers={"Content-Type": "application/json"},
        cookies=cookies,
        verify=False,
        timeout=15,
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch devices. Status code: {response.status_code}")
        raise KeyError("Failed to retrieve device data from UniFi controller.")


# Extract LACP/LAG data from the UniFi device response
def extract_unifi_lags(unifi_data):
    unifi_lags = []

    # Level 1: loop over every device in the response (switches, APs, gateways, etc.)
    for device in unifi_data["data"]:
        # skip anything that isn't a UniFi switch
        if device["type"] != "usw":
            continue

        # build a port number -> port dict so I can look up any port instantly later
        port_lookup = {}
        for port in device["port_table"]:
            port_lookup[port["port_idx"]] = port

        # Level 2: loop over every port on the switch
        for port in device["port_table"]:
            # skip regular switch ports 
            if port["op_mode"] != "aggregate":
                continue

            # pull LAG-level fields from the lead port (e.g. port 7)
            # partner_system_id and service_mac_table are the MACs of the Proxmox bond NICs
            lag = {
                "switch": device["name"],
                "lag_idx": port["lag_idx"],
                "lead_port": port["port_idx"],
                "partner_system_id": port["partner_system_id"],
                "partner_macs": [m["mac"] for m in port["service_mac_table"]],
                "up": port["up"],
                "speed": port["speed"],
                "link_down_count": port["link_down_count"],
                "rx_bytes": port["rx_bytes"],
                "tx_bytes": port["tx_bytes"],
                "rx_errors": port["rx_errors"],
                "tx_errors": port["tx_errors"],
                "rx_dropped": port["rx_dropped"],
                "tx_dropped": port["tx_dropped"],
                "members": [],
            }

            # Level 3: loop over each member in lacp_state (one entry per physical port in the bundle)
            # lacp_state lives only on the lead port and contains active/speed for each member
            # I cross-reference port_lookup to get the full traffic counters for each member port
            for member in port["lacp_state"]:
                member_port = port_lookup[member["member_port"]]
                lag["members"].append({
                    "port": member["member_port"],
                    "active": member["active"],           # from lacp_state
                    "speed": member["speed"],             # from lacp_state
                    "up": member_port["up"],              # from the physical port entry
                    "link_down_count": member_port["link_down_count"],
                    "rx_bytes": member_port["rx_bytes"],
                    "tx_bytes": member_port["tx_bytes"],
                    "rx_errors": member_port["rx_errors"],
                    "tx_errors": member_port["tx_errors"],
                    "rx_dropped": member_port["rx_dropped"],
                    "tx_dropped": member_port["tx_dropped"],
                })

            unifi_lags.append(lag)

    return unifi_lags


# Fetch all network interface data from the Proxmox API
def get_proxmox_network():
    response = requests.get(
        f"{proxmox_url}/network",
        headers={"Authorization": f"PVEAPIToken={proxmox_auth}"},
        verify=False,
        timeout=15,
    )

    if response.status_code == 200:
        print("Retrieved Proxmox network information.")
        return response.json()
    else:
        print(f"Failed to retrieve Proxmox network information. Status code: {response.status_code}")
        raise KeyError("Check your Proxmox API credentials and try again.")


# Extract bond data from the Proxmox network response
def extract_proxmox_bonds(proxmox_data):
    proxmox_bonds = []

    # Level 1: loop over every network interface Proxmox knows about
    # this includes eth, bond, and bridge entries all mixed together
    for interface in proxmox_data["data"]:

        # skip anything that isn't a bond (eth interfaces, bridges, etc.)
        if interface["type"] != "bond":
            continue

        # pull bond-level fields from the bond entry
        # slaves is a space-separated string e.g. "eno1 eno2 eno3 eno4" so we split it into a list
        bond = {
            "iface": interface["iface"],
            "slaves": interface["slaves"].split(),
            "hashpolicy": interface["bond_xmit_hash_policy"],
            "mode": interface["bond_mode"],
            "active": interface["active"],
            "options": interface["options"],
        }

        slave_macs = []

        # Level 2a: loop over all interfaces again to find the eth entries that belong to this bond
        # we match on iface name being in the bond's slaves list
        for iface in proxmox_data["data"]:

            if iface["type"] != "eth":
                continue

            # skip eth interfaces that aren't a slave of this bond
            if iface["iface"] not in bond["slaves"]:
                continue

            # altnames[1] is the MAC-based name e.g. "enx1866daf1f484"
            # strip the "enx" prefix then insert colons every 2 characters to get a proper MAC
            raw = iface["altnames"][1].removeprefix("enx")
            mac = ":".join(raw[i:i+2] for i in range(0, len(raw), 2))
            slave_macs.append(mac)

        # Level 2b: loop over all interfaces again to find the bridge sitting on top of this bond
        # the bridge holds the IP address, CIDR, and gateway for the bond
        for iface in proxmox_data["data"]:
            if iface["type"] != "bridge":
                continue

            # match the bridge to this bond by checking bridge_ports == bond interface name
            if iface["bridge_ports"] == bond["iface"]:
                bond["address"] = iface["address"]
                bond["cidr"] = iface["cidr"]
                bond["gateway"] = iface["gateway"]

        bond["slave_macs"] = slave_macs
        proxmox_bonds.append(bond)

    return proxmox_bonds


def get_matching_bond(unifi_lag, proxmox_bonds, used_bonds):
    lag_macs = set(unifi_lag["partner_macs"])
    available_bonds = [bond for bond in proxmox_bonds if bond["iface"] not in used_bonds]

    for bond in available_bonds:
        if lag_macs == set(bond["slave_macs"]):
            return bond

    ranked_bonds = sorted(
        available_bonds,
        key=lambda bond: len(lag_macs & set(bond["slave_macs"])),
        reverse=True,
    )

    if ranked_bonds and lag_macs & set(ranked_bonds[0]["slave_macs"]):
        return ranked_bonds[0]

    return None


def get_health_checks(unifi_lag, proxmox_bond):
    no_errors = (
        unifi_lag["rx_errors"] == 0
        and unifi_lag["tx_errors"] == 0
        and unifi_lag["rx_dropped"] == 0
        and unifi_lag["tx_dropped"] == 0
        and all(
            member["rx_errors"] == 0
            and member["tx_errors"] == 0
            and member["rx_dropped"] == 0
            and member["tx_dropped"] == 0
            for member in unifi_lag["members"]
        )
    )

    return [
        ("MACs match on both sides", set(unifi_lag["partner_macs"]) == set(proxmox_bond["slave_macs"])),
        ("All members active", all(member["active"] for member in unifi_lag["members"])),
        ("Consistent speeds across members", len(set(member["speed"] for member in unifi_lag["members"])) == 1),
        ("LAG is up on both sides", unifi_lag["up"] is True and proxmox_bond["active"] == 1),
        ("Bond mode is 802.3ad", proxmox_bond["mode"] == "802.3ad"),
        ("No errors or drops detected", no_errors),
    ]


def get_health_findings(unifi_lag, proxmox_bond):
    findings = []

    if set(unifi_lag["partner_macs"]) != set(proxmox_bond["slave_macs"]):
        findings.append("Partner MACs do not fully match the Proxmox bond slaves.")

    inactive_members = [member["port"] for member in unifi_lag["members"] if not member["active"]]
    if inactive_members:
        findings.append(f"Inactive switch members detected: {', '.join(map(str, inactive_members))}.")

    member_speeds = {member["speed"] for member in unifi_lag["members"]}
    if len(member_speeds) > 1:
        findings.append("Member link speeds are inconsistent across the LAG.")

    if not unifi_lag["up"] or proxmox_bond["active"] != 1:
        findings.append("The LAG is not up on both the switch and Proxmox.")

    if proxmox_bond["mode"] != "802.3ad":
        findings.append(f"Bond mode is {proxmox_bond['mode']} instead of 802.3ad.")

    noisy_members = [
        str(member["port"])
        for member in unifi_lag["members"]
        if any(
            member[counter] > 0
            for counter in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped")
        )
    ]
    if noisy_members:
        findings.append(f"Errors or drops were reported on switch ports: {', '.join(noisy_members)}.")

    if any(unifi_lag[counter] > 0 for counter in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped")):
        findings.append("Aggregate LAG counters show errors or drops.")

    return findings


# Compare a UniFi LAG against a Proxmox bond and print a health report
def print_health_report(unifi_lag, proxmox_bond):
    checks = get_health_checks(unifi_lag, proxmox_bond)
    findings = get_health_findings(unifi_lag, proxmox_bond)

    if not next(result for label, result in checks if label == "LAG is up on both sides"):
        status = "DOWN"
    elif all(result for _, result in checks):
        status = "HEALTHY"
    else:
        status = "DEGRADED"

    print("=== LAG HEALTH REPORT ===")
    print()
    print(f"Switch:  {unifi_lag['switch']}    LAG {unifi_lag['lag_idx']}")
    print(f"Bond:    {proxmox_bond['iface']}    {proxmox_bond.get('cidr', 'unassigned')}")
    print(f"Gateway: {proxmox_bond.get('gateway', 'unassigned')}")
    print()

    print(f"STATUS: {status}")
    print()

    print("CHECKS")
    for label, result in checks:
        print(f"  {'[OK]' if result else '[WARN]'}   {label}")
    print()

    print("FINDINGS")
    if findings:
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("  - No mismatches detected.")
    print()

    print("MEMBERS")
    for member in unifi_lag["members"]:
        state = "active" if member["active"] else "inactive"
        status = "UP" if member["up"] else "DOWN"
        print(f"  Port {member['port']}   {status}   {state}   {member['speed']}Mbps")


def print_unmatched_lag(unifi_lag):
    print("=== LAG HEALTH REPORT ===")
    print()
    print(f"Switch:  {unifi_lag['switch']}    LAG {unifi_lag['lag_idx']}")
    print("Bond:    No matching Proxmox bond found")
    print()
    print("STATUS: DEGRADED")
    print()
    print("FINDINGS")
    print("  - Unable to correlate this UniFi LAG to a Proxmox bond using MAC addresses.")


def print_unmatched_bond(proxmox_bond):
    print("=== LAG HEALTH REPORT ===")
    print()
    print(f"Bond:    {proxmox_bond['iface']}    {proxmox_bond.get('cidr', 'unassigned')}")
    print()
    print("STATUS: DEGRADED")
    print()
    print("FINDINGS")
    print("  - This Proxmox bond did not match any UniFi LAG partner MACs.")


def main():
    unifi_cookies = get_unifi_cookie()
    unifi_data = get_unifi_devices(unifi_cookies)
    unifi_lags = extract_unifi_lags(unifi_data)

    proxmox_data = get_proxmox_network()
    proxmox_bonds = extract_proxmox_bonds(proxmox_data)

    if not unifi_lags:
        print("No UniFi LAGs were found.")
        return

    if not proxmox_bonds:
        print("No Proxmox bonds were found.")
        return

    used_bonds = set()

    for index, unifi_lag in enumerate(unifi_lags):
        matching_bond = get_matching_bond(unifi_lag, proxmox_bonds, used_bonds)

        if matching_bond is None:
            print_unmatched_lag(unifi_lag)
        else:
            used_bonds.add(matching_bond["iface"])
            print_health_report(unifi_lag, matching_bond)

        if index < len(unifi_lags) - 1:
            print()

    unmatched_bonds = [bond for bond in proxmox_bonds if bond["iface"] not in used_bonds]
    for proxmox_bond in unmatched_bonds:
        print()
        print_unmatched_bond(proxmox_bond)


if __name__ == "__main__":
    main()
