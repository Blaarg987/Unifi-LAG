import unittest

import main


class MainTests(unittest.TestCase):
    def test_get_matching_bond_prefers_exact_mac_match(self):
        unifi_lag = {
            "partner_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"],
        }
        proxmox_bonds = [
            {"iface": "bond0", "slave_macs": ["aa:aa:aa:aa:aa:aa"]},
            {"iface": "bond1", "slave_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"]},
        ]

        match = main.get_matching_bond(unifi_lag, proxmox_bonds, used_bonds=set())

        self.assertEqual("bond1", match["iface"])

    def test_get_matching_bond_skips_used_bonds(self):
        unifi_lag = {
            "partner_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"],
        }
        proxmox_bonds = [
            {"iface": "bond0", "slave_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"]},
            {"iface": "bond1", "slave_macs": ["aa:aa:aa:aa:aa:aa"]},
        ]

        match = main.get_matching_bond(unifi_lag, proxmox_bonds, used_bonds={"bond0"})

        self.assertEqual("bond1", match["iface"])

    def test_get_health_checks_marks_clean_lag_healthy(self):
        unifi_lag = {
            "partner_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"],
            "members": [
                {
                    "port": 7,
                    "active": True,
                    "speed": 1000,
                    "up": True,
                    "rx_errors": 0,
                    "tx_errors": 0,
                    "rx_dropped": 0,
                    "tx_dropped": 0,
                },
                {
                    "port": 8,
                    "active": True,
                    "speed": 1000,
                    "up": True,
                    "rx_errors": 0,
                    "tx_errors": 0,
                    "rx_dropped": 0,
                    "tx_dropped": 0,
                },
            ],
            "up": True,
            "rx_errors": 0,
            "tx_errors": 0,
            "rx_dropped": 0,
            "tx_dropped": 0,
        }
        proxmox_bond = {
            "iface": "bond0",
            "slave_macs": ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"],
            "active": 1,
            "mode": "802.3ad",
        }

        checks = dict(main.get_health_checks(unifi_lag, proxmox_bond))

        self.assertTrue(all(checks.values()))

    def test_get_health_findings_reports_specific_mismatches(self):
        unifi_lag = {
            "partner_macs": ["aa:aa:aa:aa:aa:aa"],
            "members": [
                {
                    "port": 7,
                    "active": False,
                    "speed": 1000,
                    "up": False,
                    "rx_errors": 1,
                    "tx_errors": 0,
                    "rx_dropped": 0,
                    "tx_dropped": 0,
                },
                {
                    "port": 8,
                    "active": True,
                    "speed": 10000,
                    "up": True,
                    "rx_errors": 0,
                    "tx_errors": 0,
                    "rx_dropped": 0,
                    "tx_dropped": 0,
                },
            ],
            "up": False,
            "rx_errors": 0,
            "tx_errors": 0,
            "rx_dropped": 0,
            "tx_dropped": 1,
        }
        proxmox_bond = {
            "iface": "bond0",
            "slave_macs": ["bb:bb:bb:bb:bb:bb"],
            "active": 0,
            "mode": "balance-rr",
        }

        findings = main.get_health_findings(unifi_lag, proxmox_bond)

        self.assertGreaterEqual(len(findings), 5)
        self.assertTrue(any("Partner MACs" in finding for finding in findings))
        self.assertTrue(any("Inactive switch members" in finding for finding in findings))
        self.assertTrue(any("inconsistent" in finding for finding in findings))
        self.assertTrue(any("not up" in finding for finding in findings))
        self.assertTrue(any("instead of 802.3ad" in finding for finding in findings))
        self.assertTrue(any("Errors or drops" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
