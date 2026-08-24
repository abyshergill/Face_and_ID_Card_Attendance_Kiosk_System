"""
Kiosk / machine identity resolution.

In a multi-PC deployment (many User-Mode scan kiosks + one or more Admin
dashboards, all pointed at a single centralized PostgreSQL server) the
application needs a stable way to answer "which physical machine is this
running on?" so the admin can see, label, and control access per location.

Identity is derived from two things that together uniquely identify a
station in almost all real deployments:
  - MAC address of the machine's primary network interface
  - The OS-level username the application process is running as

Both are read once per process and cached (a kiosk's network adapter and
login account do not change while the app is running).
"""
import getpass
import logging
import os
import socket
import uuid
from dataclasses import dataclass

logger = logging.getLogger("attendance.kiosk_identity")


@dataclass(frozen=True)
class KioskIdentity:
    mac_address: str
    machine_username: str
    hostname: str


def _resolve_mac_address() -> str:
    try:
        node = uuid.getnode()
        # uuid.getnode() falls back to a random 48-bit number (with the
        # multicast bit set) when it cannot determine a real MAC address.
        # That random value has bit 0 of the first octet set to 1.
        if (node >> 40) % 2 == 1:
            logger.warning("Could not resolve a real MAC address; using a fallback identifier.")
        mac = ":".join(f"{(node >> ele) & 0xff:02X}" for ele in range(40, -1, -8))
        return mac
    except Exception:
        logger.exception("Failed to resolve MAC address.")
        return "UNKNOWN-MAC"


def _resolve_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown-user"


def _resolve_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


_identity = None


def get_identity() -> KioskIdentity:
    """Returns (and caches) the identity of the machine this process is running on."""
    global _identity
    if _identity is None:
        _identity = KioskIdentity(
            mac_address=_resolve_mac_address(),
            machine_username=_resolve_username(),
            hostname=_resolve_hostname(),
        )
        logger.info(
            "Resolved kiosk identity: MAC=%s, user=%s, host=%s",
            _identity.mac_address, _identity.machine_username, _identity.hostname,
        )
    return _identity
