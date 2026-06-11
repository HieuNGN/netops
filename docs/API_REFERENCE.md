# NetOps API Reference

Complete endpoint listing, type definitions, and channel configs.

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with poller + alert stats |
| `GET` | `/metrics` | Prometheus metrics |
| **Topology** | | |
| `GET` | `/topology` | Current nodes & links |
| `GET` | `/topology/stream` | SSE stream for live updates |
| `POST` | `/topology/refresh` | Trigger immediate SNMP poll |
| `POST` | `/topology/simulate` | Generate demo network graph |
| `GET` | `/topology/history` | Topology change audit log |
| **Devices** | | |
| `GET` | `/devices` | List all devices |
| `POST` | `/devices` | Add device to monitor |
| `GET/PUT/DELETE` | `/devices/{id}` | CRUD operations |
| `POST` | `/devices/{dId}/network/{nId}` | Assign device to network |
| `POST` | `/discover` | Scan subnet for SNMP devices |
| **Networks** | | |
| `GET` | `/networks` | List networks with device counts |
| `GET/PUT/DELETE` | `/networks/{id}` | Manage network (name, type, tags, CIDR) |
| `POST` | `/networks` | Create network |
| `POST` | `/networks/{id}/default` | Set as default |
| **Service Checks** | | |
| `GET/POST` | `/checks` | List / create checks |
| `GET/PUT/DELETE` | `/checks/{id}` | CRUD operations |
| `POST` | `/checks/{id}/run` | Execute check immediately |
| `GET` | `/checks/{id}/results` | Check result history |
| `GET` | `/checks/stats` | Scheduler statistics |
| **Alerts** | | |
| `GET/POST` | `/alerts` | List / create alert configs |
| `GET` | `/alerts/history` | Recent alert activity |
| `GET` | `/alerts/active` | Currently firing alerts |
| `POST` | `/alerts/active/{k}/acknowledge` | Ack an alert |
| `POST` | `/alerts/active/{k}/resolve` | Resolve an alert |
| `POST` | `/alerts/{id}/test` | Send test notification |
| **Maintenance** | | |
| `GET/POST` | `/maintenance-windows` | List / schedule downtime |
| `DELETE` | `/maintenance-windows/{id}` | Remove window |
| `GET` | `/poll-history` | Recent SNMP poll results |
| `GET` | `/stats` | Poller throughput stats |

## Network Types

| Slug | Label | Description |
|------|-------|-------------|
| `lan` | LAN | Wired local area network |
| `wan` | WAN | Wide area / uplink |
| `wifi` | Wi-Fi | Wireless 802.11 |
| `sfp` | SFP / Fiber | Optical fiber |
| `console` | Console / Serial | RS-232 management port |
| `bmc` | BMC / IPMI | Out-of-band controller |
| `mgmt` | Management | OOB management network |
| `dmz` | DMZ | Perimeter zone |
| `vlan` | VLAN | Logical segment |
| `vpn` | VPN | Encrypted tunnel |
| `custom` | Custom | Unclassified |

## Service Check Types

| Type | Description |
|------|-------------|
| `http` | HTTP/HTTPS endpoint — status code, response body |
| `tcp` | Raw TCP port connectivity |
| `dns` | DNS resolution — record type, expected IPs |
| `ping` | ICMP echo — latency, packet loss |
| `ssl` | SSL certificate expiry — warning/critical day thresholds |

## Notification Channels

| Channel | Transport |
|---------|-----------|
| `slack` | Incoming webhook |
| `telegram` | Bot API |
| `whatsapp` | Twilio API |
| `email` | SMTP |
| `webhook` | Generic HTTP POST |
