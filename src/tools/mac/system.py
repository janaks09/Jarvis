"""macOS system status - battery, disk, memory, Wi-Fi, VPN.

All read-only commands; safe to call any time. Returns a single
voice-friendly summary string by default, or just the metric the user
asked about.
"""

import asyncio
import logging
import re
from typing import Literal

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_command

logger = logging.getLogger(__name__)

Metric = Literal["all", "battery", "disk", "memory", "wifi", "vpn"]


async def _battery() -> str:
    rc, out, _ = await run_command("pmset", "-g", "batt", timeout=5.0)
    if rc != 0 or not out:
        return "Battery: unavailable."
    # Example line:
    #   -InternalBattery-0 (id=...)\t 84%; discharging; 5:12 remaining present: true
    pct_match = re.search(r"(\d+)%", out)
    state_match = re.search(r";\s*([a-zA-Z ]+);", out)
    time_match = re.search(r"(\d+:\d+) remaining", out)
    if not pct_match:
        return "Battery: unavailable."
    pct = pct_match.group(1)
    state = state_match.group(1).strip() if state_match else "unknown"
    if time_match:
        return f"Battery: {pct}%, {state}, {time_match.group(1)} remaining."
    return f"Battery: {pct}%, {state}."


async def _disk() -> str:
    rc, out, _ = await run_command("df", "-H", "/", timeout=5.0)
    if rc != 0 or not out:
        return "Disk: unavailable."
    lines = out.splitlines()
    if len(lines) < 2:
        return "Disk: unavailable."
    parts = lines[1].split()
    if len(parts) < 5:
        return "Disk: unavailable."
    size, _used, avail, capacity = parts[1], parts[2], parts[3], parts[4]
    return f"Disk: {avail} free of {size} ({capacity} used)."


async def _memory() -> str:
    rc, out, _ = await run_command("memory_pressure", timeout=5.0)
    if rc != 0 or not out:
        return "Memory: unavailable."
    free_match = re.search(r"System-wide memory free percentage:\s*(\d+)%", out)
    pressure_match = re.search(
        r"The system has (\w+) memory pressure", out, re.IGNORECASE
    )
    if not free_match:
        return "Memory: unavailable."
    free_pct = free_match.group(1)
    pressure = pressure_match.group(1).lower() if pressure_match else "unknown"
    return f"Memory: {free_pct}% free, pressure is {pressure}."


async def _wifi() -> str:
    # Find the active Wi-Fi interface (usually en0).
    rc, out, _ = await run_command(
        "networksetup", "-listallhardwareports", timeout=5.0
    )
    iface = "en0"
    if rc == 0 and out:
        m = re.search(
            r"Hardware Port:\s*Wi-?Fi\s*\nDevice:\s*(\w+)", out, re.IGNORECASE
        )
        if m:
            iface = m.group(1)

    rc, out, _ = await run_command(
        "networksetup", "-getairportnetwork", iface, timeout=5.0
    )
    if rc != 0 or not out:
        return "Wi-Fi: unavailable."
    if "not associated" in out.lower() or "off" in out.lower():
        return "Wi-Fi: not connected."
    # "Current Wi-Fi Network: <SSID>"
    m = re.search(r":\s*(.+)$", out.strip())
    if m:
        return f"Wi-Fi: connected to {m.group(1).strip()}."
    return f"Wi-Fi: {out.strip()}"


async def _vpn() -> str:
    rc, out, _ = await run_command("scutil", "--nc", "list", timeout=5.0)
    if rc != 0 or not out:
        return "VPN: unavailable."
    connected = [
        line for line in out.splitlines() if line.startswith("* (Connected)")
    ]
    if connected:
        # "* (Connected)  ABC123 PPP --> Service Name"
        names = []
        for line in connected:
            m = re.search(r'"([^"]+)"', line)
            names.append(m.group(1) if m else "unnamed")
        return f"VPN: connected ({', '.join(names)})."
    return "VPN: not connected."


_FETCHERS = {
    "battery": _battery,
    "disk": _disk,
    "memory": _memory,
    "wifi": _wifi,
    "vpn": _vpn,
}


@function_tool(
    name="system_status",
    description=(
        "Get a snapshot of the user's Mac status - battery, disk, "
        "memory, Wi-Fi, VPN. Use when the user asks 'what's my battery "
        "at?', 'how much disk do I have?', 'what's my memory like?', "
        "'am I on Wi-Fi?', 'am I on VPN?', or 'how's my system?'.\n\n"
        "`metric` selects what to return:\n"
        "  - 'all' (default): one-line summary of every metric\n"
        "  - 'battery' / 'disk' / 'memory' / 'wifi' / 'vpn': just that\n\n"
        "Read-only and fast (~100ms). Safe to call repeatedly."
    ),
)
async def system_status(
    context: RunContext, metric: Metric = "all"
) -> str:
    if msg := macos_only("System status"):
        return msg

    if metric != "all":
        fn = _FETCHERS.get(metric)
        if fn is None:
            return f"Unknown metric '{metric}'."
        return await fn()

    # Run all fetchers concurrently.
    results = await asyncio.gather(*(fn() for fn in _FETCHERS.values()))
    return " ".join(results)


SYSTEM_TOOLS = [system_status]
