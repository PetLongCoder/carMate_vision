"""局域网 IP 检测，供微信扫码等场景使用。"""

from __future__ import annotations

import platform
import re
import socket
import subprocess


_VIRTUAL_PREFIXES = (
    "127.",
    "169.254.",
    "192.168.60.",
    "192.168.65.",
)

_WLAN_KEYWORDS = ("WLAN", "无线", "Wi-Fi", "WiFi", "Wireless")


def _is_usable_ip(ip: str) -> bool:
    return not ip.startswith(_VIRTUAL_PREFIXES)


def _pick_from_ipconfig() -> str | None:
    if platform.system() != "Windows":
        return None

    try:
        output = subprocess.check_output(["ipconfig"], encoding="gbk", errors="ignore")
    except (OSError, subprocess.SubprocessError):
        return None

    wlan_ips: list[str] = []
    other_ips: list[str] = []

    for section in re.split(r"\n\s*\n", output):
        if "IPv4" not in section:
            continue

        match = re.search(r"IPv4[^:]*:\s*([\d.]+)", section)
        if not match:
            continue

        ip = match.group(1)
        if not _is_usable_ip(ip):
            continue

        if any(keyword in section for keyword in _WLAN_KEYWORDS):
            wlan_ips.append(ip)
        else:
            other_ips.append(ip)

    if wlan_ips:
        return wlan_ips[0]
    if other_ips:
        return other_ips[0]
    return None


def _pick_from_socket() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if _is_usable_ip(ip):
            return ip
    except OSError:
        return None
    return None


def detect_lan_ip() -> str:
    """优先 WLAN，其次其他网卡，最后 socket 探测。"""
    return _pick_from_ipconfig() or _pick_from_socket() or "127.0.0.1"
