This project was written by me for use in my own homelab and to practice my Python dev skills. This program does the following:

1. Uses the Unifi and Proxmox API to retrieve LAG / Interface details in JSON format.
2. Parses them to retrieve the relevant key/value pairs and add them to new dictionarys
3. Compare the values to derive health data from the LACP statuses and print the values (eg. Link Speeds, MAC addresses matching on both sides, LAG members, IP Address, State, etc).

If anyone has the same lab setup as me (Proxmox + Unifi) they are free to use this and or modify it to suit there needs. 
