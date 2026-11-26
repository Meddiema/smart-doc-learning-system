import re
from statistics import mean

HOP_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(?:([^\s(]+)\s*\(([^)]+)\)|([^\s*]+))?(.*)$"
)
RTT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
HEADER_RE = re.compile(
    r"tracing route to\s+([^\s(]+)(?:\s*\(([^)]+)\))?,\s*(\d+)\s+hops\s+max",
    re.IGNORECASE,
)

FLAG_NOTES = {
    "-sS": "TCP SYN ('stealth') scan — sends SYN without completing full TCP handshake; requires raw socket privileges.",
    "-sT": "TCP Connect scan — uses OS `connect()` syscall; noisier in logs but works without raw sockets.",
    "-sV": "Service/version detection — probes open ports to fingerprint banners and versions.",
    "-sC": "Default NSE script scan — runs safe/standard enumeration scripts against discovered services.",
    "-A": "Aggressive scan — combines OS detection, version probing, script scanning, and traceroute (high traffic/noise).",
    "-Pn": "Skip host discovery — treats hosts as online even if ping/ICMP is blocked; can slow scans on dead subnets.",
    "-O": "Remote OS fingerprinting — infers OS via TCP/IP stack behavior.",
    "-T4": "Aggressive timing template — speeds up scans on reliable networks; risk of packet loss or IDS throttling on slow links.",
    "-iL": "Input list — reads target hosts/CIDRs from a file (verify every target is strictly in scope).",
    "-oN": "Normal output — saves readable scan results to a file for later review.",
    "-oX": "XML output — saves structured scan output for parsing or reporting.",
}


def extract_command_line(raw_text: str) -> str:
    """Extract the primary CLI command if present in the input block."""
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$ "):
            return stripped[2:].strip()
        if re.match(r"^(nmap|traceroute|tracert|ping|mtr|dig|nslookup|host|whois|curl|wget|ss|netstat|ip|chmod|chown|find|ps|id|sudo|ssh|nc|ncat|smbclient|sqlmap|ffuf|gobuster|nikto)\b", stripped, re.IGNORECASE):
            return stripped
    return ""


def detect_command_family(command_line: str, raw_text: str) -> str:
    """Classify the command or output into a practical ethical-hacking domain."""
    combined = f"{command_line}\n{raw_text}".lower()
    cmd_head = (command_line.split()[0].lower() if command_line.split() else "")

    if cmd_head in {"traceroute", "tracert", "mtr"} or "tracing route to" in combined:
        return "route_path"
    if cmd_head == "nmap" or "nmap scan report" in combined:
        return "port_service_recon"
    if cmd_head in {"dig", "nslookup", "host", "whois"} or "question section" in combined or "answer section" in combined:
        return "dns_recon"
    if cmd_head in {"curl", "wget", "ffuf", "gobuster", "nikto", "sqlmap"} or combined.startswith("http/"):
        return "web_http_recon"
    if cmd_head in {"ss", "netstat", "ip", "nc", "ncat", "ssh"} or "tcp " in combined or "udp " in combined:
        return "socket_session_inspect"
    if cmd_head in {"chmod", "chown", "find", "ps", "id", "sudo", "ls"}:
        return "host_hardening_ops"
    return "general_cli"


def explain_flags_and_args(command_line: str) -> list[str]:
    """Extract notable flags and arguments from a CLI command."""
    if not command_line:
        return []
    tokens = command_line.split()
    notes = []

    for i, tok in enumerate(tokens[1:], start=1):
        if tok in FLAG_NOTES:
            notes.append(f"`{tok}`: {FLAG_NOTES[tok]}")
        elif tok.startswith("-p") and len(tok) > 2:
            notes.append(f"`{tok}`: Targets specific port(s)/range `{tok[2:]}` instead of default top ports.")
        elif tok == "-p" and i + 1 < len(tokens):
            notes.append(f"`-p {tokens[i + 1]}`: Targets specific port(s)/range `{tokens[i + 1]}`.")
        elif not tok.startswith("-") and i == len(tokens) - 1:
            notes.append(f"Target / argument: `{tok}` — confirm explicit authorization before probing external assets.")

    return notes


def parse_traceroute_output(raw_text: str) -> dict:
    """Parse traceroute / tracert output into structured hop metrics and findings."""
    lines = [ln.rstrip() for ln in (raw_text or "").splitlines() if ln.strip()]
    target_host = ""
    target_ip = ""
    max_hops = None
    hops = []
    prev_avg = None

    for line in lines:
        hdr = HEADER_RE.search(line)
        if hdr:
            target_host = hdr.group(1).strip()
            target_ip = (hdr.group(2) or "").strip()
            max_hops = int(hdr.group(3))
            continue

        m = HOP_LINE_RE.match(line)
        if not m:
            continue

        hop_num = int(m.group(1))
        hostname = (m.group(2) or m.group(4) or "").strip()
        ip_addr = (m.group(3) or "").strip()
        rest = m.group(5) or ""

        if not ip_addr and re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", hostname):
            ip_addr = hostname
            hostname = ""

        rtts = [float(val) for val in RTT_RE.findall(rest)]
        star_count = rest.count("*")
        timed_out = "timed out" in rest.lower() or (len(rtts) == 0 and star_count >= 1)

        avg_rtt = round(mean(rtts), 2) if rtts else None
        jitter_rtt = round(max(rtts) - min(rtts), 2) if len(rtts) >= 2 else None
        delta_from_prev = (
            round(avg_rtt - prev_avg, 2)
            if (avg_rtt is not None and prev_avg is not None)
            else None
        )

        if avg_rtt is not None:
            prev_avg = avg_rtt

        reached_target = bool(
            (target_ip and ip_addr == target_ip)
            or (target_host and hostname.lower() == target_host.lower())
        )

        hops.append(
            {
                "hop": hop_num,
                "hostname": hostname or ("*" if timed_out else "N/A"),
                "ip": ip_addr or ("*" if timed_out else "N/A"),
                "rtts_ms": rtts,
                "avg_ms": avg_rtt,
                "jitter_ms": jitter_rtt,
                "delta_ms": delta_from_prev,
                "stars": star_count,
                "timed_out": timed_out,
                "reached_target": reached_target,
                "raw": line.strip(),
            }
        )

    findings = []
    for h in hops:
        if h["delta_ms"] is not None and h["delta_ms"] >= 100.0:
            findings.append(
                f"Hop {h['hop']} ({h['hostname']} / {h['ip']}) jumps by +{h['delta_ms']} ms (avg {h['avg_ms']} ms) — possible link congestion, geographic/transit hop, or ICMP/TTL control-plane rate-limiting."
            )
        if h["jitter_ms"] is not None and h["jitter_ms"] >= 80.0:
            findings.append(
                f"Hop {h['hop']} shows {h['jitter_ms']} ms RTT spread across probes ({h['rtts_ms']} ms) — indicates variable queueing or router rate-limiting."
            )
        if h["timed_out"]:
            findings.append(
                f"Hop {h['hop']} ({h['hostname']} / {h['ip']}) timed out — edge firewall/ACL may drop or deprioritize traceroute probes even if service ports are reachable."
            )

    reached_dest = any(h["reached_target"] for h in hops)
    if hops and not reached_dest:
        last_hop = hops[-1]
        findings.append(
            f"Trace stopped at Hop {last_hop['hop']} without a direct probe reply from {target_host or target_ip} — verify actual service reachability with a targeted protocol/port check."
        )

    return {
        "target_host": target_host or "Unknown Target",
        "target_ip": target_ip or "Unknown IP",
        "max_hops": max_hops,
        "hops": hops,
        "findings": findings,
        "reached_dest": reached_dest,
    }


def analyze_command_input(raw_text: str) -> dict:
    """Analyze any ethical-hacking or CLI command/output block with deep technical guidance."""
    command_line = extract_command_line(raw_text)
    family = detect_command_family(command_line, raw_text)
    flag_notes = explain_flags_and_args(command_line)
    traceroute_data = parse_traceroute_output(raw_text) if family == "route_path" else None

    family_summaries = {
        "route_path": (
            "Maps Layer-3 hop path and round-trip latency toward a destination using incremental TTL/hop probes. "
            "In pentesting/recon, it helps identify ISP/transit boundaries, edge gateways, and where packets drop or get filtered."
        ),
        "port_service_recon": (
            "Discovers exposed network ports, service banners, and potential attack surface. "
            "Always distinguish `open` (accepting connections), `filtered` (firewall/ACL dropping or rejecting probes), and `closed`."
        ),
        "dns_recon": (
            "Queries DNS records (`A`, `AAAA`, `MX`, `TXT`, `NS`, `CNAME`) or domain registration data to map subdomains, mail/SPF/DMARC posture, and cloud/CDN ownership."
        ),
        "web_http_recon": (
            "Interacts with HTTP/HTTPS endpoints, headers, status codes, or paths. Watch for CDN/WAF challenges, redirects, and rate-limiting before interpreting response behavior as app logic."
        ),
        "socket_session_inspect": (
            "Inspects active sockets, listening daemons, routing tables, or remote sessions to see what services are bound locally and which peers are connected."
        ),
        "host_hardening_ops": (
            "Inspects or modifies local OS permissions, processes, privileges, or file paths—key for privilege-escalation checks, configuration auditing, and safe host administration."
        ),
        "general_cli": (
            "General command-line or tool output. Break down the command syntax, inspect exit status/error messages, and verify assumptions against a controlled test case."
        ),
    }

    safety_notes = [
        "Confirm written authorization and exact IP/domain/CIDR scope before running active scans or probes against any system you do not own.",
        "Avoid high-rate scans or intrusive scripts on production or third-party links where packet spikes or rate-limiting can skew results or cause service impact.",
    ]

    if family == "route_path" and traceroute_data:
        next_steps = [
            f"Run sustained latency sampling (`ping -c 10 {traceroute_data['target_ip'] if traceroute_data['target_ip'] != 'Unknown IP' else traceroute_data['target_host']}`) to separate one-off spikes from persistent packet loss or jitter.",
            "Test the actual application port (e.g., TCP 443/80/22) when a gateway times out on ICMP/UDP traceroute—firewalls frequently drop diagnostic probes while allowing legitimate traffic.",
        ]
    elif family == "port_service_recon":
        next_steps = [
            "Correlate open ports with exact service versions (`-sV`) and verify whether `filtered` ports come from a host firewall, network ACL, or WAF.",
            "Avoid running `-A` or broad vulnerability scripts blindly until you confirm the host is in scope and note rate limits.",
        ]
    else:
        next_steps = [
            "Cross-check the output with a second independent command (for example, pairing DNS lookup with HTTP header/TLS inspection or socket listing).",
            "Log exact commands, timestamps, and observations so findings are reproducible during reporting or remediation.",
        ]

    findings = list(traceroute_data["findings"]) if traceroute_data else []
    if not findings and not raw_text.strip():
        findings.append("No command or output provided yet.")

    return {
        "command_line": command_line or "(Output / snippet only — no command prompt detected)",
        "family": family,
        "overview": family_summaries.get(family, family_summaries["general_cli"]),
        "flag_notes": flag_notes,
        "findings": findings,
        "safety_notes": safety_notes,
        "next_steps": next_steps,
        "traceroute": traceroute_data,
    }


def format_command_report_markdown(analysis: dict, raw_text: str, ai_insight: str = "") -> str:
    """Render a comprehensive Markdown report for UI display and cheat-sheet export."""
    lines = [
        "# 🛡️ Ethical Hacking Command & Output Analysis",
        f"- **Command:** `{analysis['command_line']}`",
        f"- **Category:** `{analysis['family']}`",
        "",
        "## What This Command Does",
        analysis["overview"],
    ]

    if analysis["flag_notes"]:
        lines.extend(["", "## Flags & Arguments Breakdown"])
        for note in analysis["flag_notes"]:
            lines.append(f"- {note}")

    if analysis["findings"]:
        lines.extend(["", "## Key Output Observations"])
        for item in analysis["findings"]:
            lines.append(f"- {item}")

    lines.extend(["", "## Operational & Ethical Guardrails"])
    for guard in analysis["safety_notes"]:
        lines.append(f"- {guard}")

    lines.extend(["", "## Recommended Verification Steps"])
    for step in analysis["next_steps"]:
        lines.append(f"- {step}")

    if ai_insight.strip():
        lines.extend(["", "## Deep Mentor Walkthrough", ai_insight.strip()])

    return "\n".join(lines)