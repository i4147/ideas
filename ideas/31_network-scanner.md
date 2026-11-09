# 31 — `lan-scan` (who is on my network)

> **Difficulty 3/10** · **Effort ~2 days for a worse version** · **Tier: medium**
> **Prior art: ❌ fully solved** — `nmap` (`-sn`, `-O`, `-sV`), `arp-scan`, `netdiscover`, `fping`, `avahi-browse`, `arp -a`, `nmap`'s NSE, `masscan`, and routers' own device lists.
> **Pivot required?** Yes — but it's an inventory/history pivot, not a scanning pivot.

## The problem

"I need to know what's on my LAN" is solved: `nmap -sn 192.168.1.0/24` takes 5 seconds and `arp-scan --localnet` takes one. Writing a Python scanner from scratch gets you a slower, less accurate `nmap` that requires root and trips the same IDS.

## What exists

`nmap` (port scan, OS fingerprint, service version, NSE scripts, the industry standard), `arp-scan` (fast L2 discovery, needs root), `netdiscover`, `fping -a -g` (fast ICMP sweep), `avahi-browse -a` (mDNS names — the easiest way to get friendly names), `iw`/`ip neigh` for the ARP table. Any half-decent home router also shows this in its UI.

## The pivot: change detection, not discovery

The unsolved question is *"what is new on my network since last week?"* — which needs history, not a scan:

```bash
lan-scan watch --interval 15m --store ~/.local/share/lan-scan/history.db
lan-scan diff --since 7d                 # new / departed / changed-hostname devices
lan-scan devices                         # inventory with first_seen, last_seen, vendor, names
lan-scan alert --on new-device --exec 'notify-send "new device: {ip} {mac}"'
```

That is genuinely useful for a home lab (or a shared student flat) and genuinely unserved as a small Python CLI: `nmap` has no history, and consumer apps are cloud-connected.

Data to keep per device: MAC (primary key — IPs change), first/last seen, vendor (from the IEEE OUI database, cached locally as a ~2 MB file), observed hostnames (from reverse DNS, mDNS `_services._dns-sd._udp`, DHCP lease files `/var/lib/misc/dnsmasq.leases`, NetBIOS on port 137 — all read-only, best-effort), open ports seen (only with `--ports`, opt-in), and a fingerprint hash of the port set so "same IP, different device" is detectable.

## Implementation

Do **not** write a raw-socket ARP scanner. Shell out to what exists:

- `ip neigh show` (unprivileged, free) → known neighbours.
- `nmap -sn -oG -` or `fping -a -g` to populate the ARP cache, then re-read `ip neigh`.
- Optional `--deep`: `nmap -sV --top-ports 100 -oX -` per host, parsed as XML (never parse text output).
- mDNS: a tiny `socket` UDP query for `_services._dns-sd._udp.local` PTR — 30 lines, no dependency, gets you `raspberrypi.local` style names without root.

Schedule with a systemd timer example in the docs; the tool itself should run once and exit (`watch` = a loop with a lock file).

## Tests

Parse captured `ip neigh`, `nmap` XML, and lease files as fixtures (no network). Integration tests marked `@pytest.mark.net` that run against `127.0.0.1` and a fake `/24` on a loopback bridge, skipped by default. Assert: MAC reused with a new IP is the same device; a changed port set updates `fingerprint`; `diff --since` picks the right records with a frozen clock.

## Pitfalls

- Scanning networks you don't own is legally and ethically bad; refuse unless `--local-subnet` matches an interface's own subnet, and say why in `--help`.
- `nmap` isn't installed everywhere: detect it and degrade to `ip neigh` + ping sweep instead of failing.
- MAC randomization: phones rotate MACs — don't spam "new device" (dedupe by hostname + vendor + first-seen within 24 h, note the randomization).
- IPv6 neighbour discovery gives MACs too (`ip -6 neigh`); include it, and don't assume `/24`.
- OUI database licensing: IEEE's public list is fine to bundle; keep it in its own file so it can be updated.

## Definition of done

Weekly history of a 30-device home network with correct new/departed detection, zero root requirement in the default path, and a systemd timer that has been running for a month.
