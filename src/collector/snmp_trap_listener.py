"""SNMPv2c Trap Listener — receives linkUp / linkDown traps via UDP/162.

Phase 4 of the locked spec (PHASE4_SNMP_TRAPS_SPEC.md). Traps
provide sub-second topology updates vs. the 30-60s polling
cadence. The listener only processes standard linkUp
(1.3.6.1.6.3.1.1.5.4) and linkDown (1.3.6.1.6.3.1.1.5.3) traps;
all other SNMPv2c traps are silently dropped.

Behavior:
- Bound to a UDP socket on the configured host:port.
- Parses the SNMPv2c Trap PDU to extract source IP, OID, and
  varbinds (ifIndex, ifDescr).
- Hands off a parsed dict to a registered handler via
  `set_trap_handler`.
- Failures to bind the socket (port already in use, no root
  privileges for port 162) are logged but do not crash the
  app. The poller continues to provide topology updates.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("netops.trap_listener")

# Standard SNMPv2c trap OIDs (from RFC 3418).
TRAP_OID_LINK_UP = "1.3.6.1.6.3.1.1.5.4"
TRAP_OID_LINK_DOWN = "1.3.6.1.6.3.1.1.5.3"
LINK_TRAP_OIDS = {TRAP_OID_LINK_UP, TRAP_OID_LINK_DOWN}


def _oid_to_trap_type(oid: str) -> Optional[str]:
    if oid == TRAP_OID_LINK_UP:
        return "link_up"
    if oid == TRAP_OID_LINK_DOWN:
        return "link_down"
    return None


class TrapProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that hands each datagram to the
    listener for parsing + dispatch.

    We use a simple custom parser instead of pulling in pysnmp
    full stack. The format we need to recognize is the SNMPv2c
    Trap PDU as defined in RFC 3416: a SEQUENCE { version, community,
    PDU { request-id, error-status, error-index, varbinds } }.

    The parser walks the BER tags until it finds the trap OID and
    any ifIndex/ifDescr varbinds. If parsing fails (e.g. SNMPv3,
    malformed bytes), the datagram is dropped silently.
    """

    def __init__(self, listener: "SNMPTrapListener"):
        self.listener = listener

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        # Hard cap on packet size. SNMP traps are small in practice
        # (typically <1kB); 8kB is generous and prevents CPU/bandwidth
        # DoS via maxed-out 65k UDP packets.
        if len(data) > self.listener._max_packet_size:
            logger.debug("Trap dropped from %s: packet too large (%d bytes)", addr, len(data))
            return
        try:
            trap = self.listener._parse_trap(data, addr)
        except Exception as e:  # noqa: BLE001 — intentionally broad
            logger.debug("Trap parse failed from %s: %s", addr, e)
            return
        if trap is None:
            return
        if self.listener._on_trap is not None:
            try:
                asyncio.create_task(self.listener._on_trap(trap))
            except RuntimeError:
                # No running loop (shouldn't happen in lifespan
                # but be defensive). Skip dispatch.
                pass


class SNMPTrapListener:
    """Async UDP listener for SNMPv2c traps.

    Lifecycle:
        listener = SNMPTrapListener(community="public")
        listener.set_trap_handler(my_handler)
        await listener.start()    # bind UDP socket
        # ... app runs, traps arrive, handler fires ...
        await listener.stop()     # close socket
    """

    def __init__(self, community: str = "public"):
        self.community = community
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[TrapProtocol] = None
        self._on_trap: Optional[Callable[[dict[str, Any]], Any]] = None
        self._running = False
        self._port: int = 162
        self._bind_host: str = "0.0.0.0"
        # Rate limit: max traps per source IP per minute.
        self._rate_limit_per_min = 100
        self._rate_window: dict[str, list[float]] = {}
        # Hard cap on the rate-window dict size to prevent memory
        # exhaustion via UDP source-IP spoofing between eviction ticks.
        # At 100k IPs (~ a few MB) we stop learning new sources and
        # keep responding to known-busy ones.
        self._rate_window_max_keys = 100_000
        # Hard cap on datagram size (defense in depth against
        # bandwidth / CPU DoS via maxed-out 65k UDP packets).
        self._max_packet_size = 8192

    def set_trap_handler(self, handler: Callable[[dict[str, Any]], Any]):
        """Register a coroutine or callable fired for each linkUp/linkDown trap."""
        self._on_trap = handler

    def configure(self, bind_host: str, port: int, community: str):
        """Update the bind target. Takes effect on the next start()."""
        self._bind_host = bind_host
        self._port = int(port)
        self.community = community

    async def start(self) -> bool:
        """Bind the UDP socket. Returns True on success, False on failure."""
        if self._running:
            return True
        loop = asyncio.get_event_loop()
        try:
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: TrapProtocol(self),
                local_addr=(self._bind_host, self._port),
            )
        except PermissionError:
            logger.warning(
                f"Cannot bind SNMP trap port {self._port} (need root/admin). "
                "Traps disabled; polling continues."
            )
            return False
        except OSError as e:
            logger.warning(f"Cannot start trap listener on {self._bind_host}:{self._port}: {e}")
            return False
        self._running = True
        # Periodic eviction of stale rate-window entries. UDP source IPs
        # are trivially spoofed, so this bounds the dict size.
        self._evict_task = asyncio.create_task(self._evict_loop())
        logger.info(f"SNMP trap listener started on {self._bind_host}:{self._port}")
        return True

    async def _evict_loop(self) -> None:
        """Periodically evict expired rate-window entries."""
        while self._running:
            try:
                await asyncio.sleep(60)
                self._evict_rate_window()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Rate-window evict error: {e}")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
        if getattr(self, "_evict_task", None):
            self._evict_task.cancel()
            try:
                await self._evict_task
            except asyncio.CancelledError:
                pass
            self._evict_task = None

    def _parse_trap(self, data: bytes, addr: tuple[str, int]) -> Optional[dict[str, Any]]:
        """Parse a raw SNMPv2c Trap PDU. Returns None if irrelevant/malformed.

        We walk the BER structure looking for:
        - community string (must match if check_community)
        - the trap OID (first varbind in the varbind list)
        - ifIndex + ifDescr (optional, but commonly present)

        BER encoding reminders:
          SEQUENCE       = 0x30 ... (constructed)
          INTEGER        = 0x02 ...
          OCTET STRING   = 0x04 ...
          OID            = 0x06 ...
          IPADDRESS      = 0x40 ...
        """
        # Drop oversized datagrams before parsing. UDP max is 65kB;
        # the largest real-world trap is well under 1kB. This is the
        # outer belt to the inner TLV-length cap.
        if len(data) > self._max_packet_size:
            return None
        oid, if_index, if_descr, community_ok = self._walk_trap(data)
        if not oid or not community_ok:
            return None
        trap_type = _oid_to_trap_type(oid)
        if trap_type is None:
            return None
        # Rate-limit per source IP.
        if not self._check_rate(addr[0]):
            return None
        return {
            "source_ip": addr[0],
            "source_port": addr[1],
            "trap_oid": oid,
            "trap_type": trap_type,
            "if_index": if_index,
            "if_descr": if_descr,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # Minimal BER walker. Returns (oid, if_index, if_descr, community_ok).
    # ------------------------------------------------------------------
    def _walk_trap(self, data: bytes) -> tuple[Optional[str], Optional[int], Optional[str], bool]:
        try:
            pos, _tag, _length, _end = self._read_tlv(data, 0)
        except (IndexError, ValueError):
            return None, None, None, False
        if pos < 0:
            return None, None, None, False
        # version INTEGER
        try:
            pos, version, _, _ = self._read_integer(data, pos)
        except (IndexError, ValueError):
            return None, None, None, False
        if pos < 0 or version != 1:  # SNMPv2c reports version=1
            return None, None, None, False
        # community OCTET STRING
        try:
            pos, community, _, _ = self._read_octet_string(data, pos)
        except (IndexError, ValueError):
            return None, None, None, False
        if pos < 0:
            return None, None, None, False
        community_ok = (community == self.community.encode())
        # PDU tag
        if pos >= len(data):
            return None, None, None, community_ok
        pdu_tag = data[pos]
        pos += 1
        # Get PDU length.
        if pos >= len(data):
            return None, None, None, community_ok
        pdu_len_size = 0
        try:
            pdu_len, pdu_len_size = self._read_length(data, pos)
        except (IndexError, ValueError):
            return None, None, None, community_ok
        if pdu_len < 0 or pdu_len > self._MAX_TLV_LEN:
            return None, None, None, community_ok
        pos += pdu_len_size
        pdu_end = pos + pdu_len
        # We only care about SNMPv2c Trap (0xa7). Other PDU types ignored.
        if pdu_tag != 0xA7:
            return None, None, None, community_ok
        # request-id, error-status, error-index (all INTEGER)
        for _ in range(3):
            try:
                pos, _, _, _ = self._read_integer(data, pos)
            except (IndexError, ValueError):
                return None, None, None, community_ok
            if pos < 0:
                return None, None, None, community_ok
        # varbinds SEQUENCE
        if pos >= pdu_end:
            return None, None, None, community_ok
        try:
            pos, _t, _l, varbinds_end = self._read_tlv(data, pos)
        except (IndexError, ValueError):
            return None, None, None, community_ok
        if pos < 0:
            return None, None, None, community_ok
        # Walk varbinds. First OID is the trap OID; subsequent OID-value
        # pairs carry ifIndex (1.3.6.1.2.1.2.2.1.1) and ifDescr
        # (1.3.6.1.2.1.2.2.1.2).
        trap_oid: Optional[str] = None
        if_index: Optional[int] = None
        if_descr: Optional[str] = None
        OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"
        OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
        # Cap iterations at the bytes remaining in the packet so a
        # maliciously-large varbinds_end can't make us loop O(n²) times
        # on a small buffer.
        _iter_cap = len(data) + 1
        _iters = 0
        while pos < varbinds_end and _iters < _iter_cap:
            _iters += 1
            try:
                pos, _t, _l, vb_end = self._read_tlv(data, pos)
            except (IndexError, ValueError):
                break
            if pos < 0:
                break
            vb_pos = pos
            # OID
            try:
                vb_pos, oid_str, _, _ = self._read_oid(data, vb_pos)
            except (IndexError, ValueError):
                pos = vb_end
                continue
            if vb_pos < 0:
                pos = vb_end
                continue
            # value (skip its tag+length)
            if vb_pos < vb_end:
                try:
                    vb_pos, _, vlen, _ = self._read_tlv(data, vb_pos)
                    if vb_pos >= 0 and vlen > 0:
                        val_bytes = data[vb_pos : min(vb_pos + vlen, vb_end)]
                    else:
                        val_bytes = b""
                except (IndexError, ValueError):
                    val_bytes = b""
            else:
                val_bytes = b""
            if trap_oid is None:
                trap_oid = oid_str
            elif oid_str == OID_IF_INDEX or oid_str.startswith(OID_IF_INDEX + "."):
                if val_bytes:
                    try:
                        if_index = int.from_bytes(val_bytes, byteorder="big", signed=False)
                    except (TypeError, ValueError):
                        pass
            elif oid_str == OID_IF_DESCR or oid_str.startswith(OID_IF_DESCR + "."):
                if val_bytes:
                    try:
                        if_descr = val_bytes.decode("utf-8", errors="replace")
                    except (TypeError, UnicodeDecodeError):
                        pass
            pos = vb_end
        return trap_oid, if_index, if_descr, community_ok

    # BER helpers --------------------------------------------------------
    # Maximum TLV value length we'll accept from an untrusted UDP
    # datagram. Anything larger is treated as malformed. The cap is
    # generous (16kB) — the largest real-world SNMP trap is well under
    # 1kB. Bounds memory + prevents a 2GB length OOM / O(n²) walk
    # when the parser uses it as a loop bound.
    _MAX_TLV_LEN = 16 * 1024

    def _read_tlv(self, data: bytes, pos: int) -> tuple[int, int, int, int]:
        """Read a TLV at pos. Returns (new_pos, tag, length, value_end)."""
        if pos + 1 > len(data):
            return -1, 0, 0, pos
        tag = data[pos]
        pos += 1
        length, size = self._read_length(data, pos)
        if length < 0 or length > self._MAX_TLV_LEN:
            return -1, tag, 0, pos
        pos += size
        # Guard against arithmetic overflow when value_end is computed.
        if pos + length < pos:
            return -1, tag, 0, pos
        return pos, tag, length, pos + length

    def _read_length(self, data: bytes, pos: int) -> tuple[int, int]:
        """Read BER length. Returns (length, bytes_consumed)."""
        if pos >= len(data):
            return -1, 0
        first = data[pos]
        if first < 0x80:
            return first, 1
        n = first & 0x7F
        if n == 0:
            return -1, 0
        if pos + 1 + n > len(data):
            return -1, 0
        val = int.from_bytes(data[pos + 1 : pos + 1 + n], byteorder="big")
        return val, 1 + n

    def _read_integer(self, data: bytes, pos: int) -> tuple[int, Optional[int], int, int]:
        new_pos, tag, length, end = self._read_tlv(data, pos)
        if new_pos < 0 or tag != 0x02 or length <= 0:
            return -1, None, 0, pos
        raw = data[new_pos:end]
        if not raw:
            return -1, 0, 0, pos
        value = int.from_bytes(raw, byteorder="big", signed=(raw[0] & 0x80) != 0)
        return end, value, tag, end

    def _read_octet_string(self, data: bytes, pos: int) -> tuple[int, bytes, int, int]:
        new_pos, tag, length, end = self._read_tlv(data, pos)
        if new_pos < 0 or tag != 0x04:
            return -1, b"", 0, pos
        return end, data[new_pos:end], tag, end

    def _read_oid(self, data: bytes, pos: int) -> tuple[int, Optional[str], int, int]:
        new_pos, tag, length, end = self._read_tlv(data, pos)
        if new_pos < 0 or tag != 0x06 or length <= 0:
            return -1, None, 0, pos
        raw = data[new_pos:end]
        try:
            if len(raw) < 1:
                return -1, None, 0, pos
            components: list[int] = []
            first = raw[0]
            components.append(first // 40)
            components.append(first % 40)
            idx = 1
            while idx < len(raw):
                # Variable-length integer, base-128, high bit = continuation.
                value = 0
                while idx < len(raw):
                    byte = raw[idx]
                    idx += 1
                    value = (value << 7) | (byte & 0x7F)
                    if not (byte & 0x80):
                        break
                components.append(value)
            return end, ".".join(str(c) for c in components), tag, end
        except (TypeError, ValueError):
            return -1, None, 0, pos

    # Rate limit ---------------------------------------------------------
    def _check_rate(self, source_ip: str) -> bool:
        now = time.time()
        # Hard cap: don't learn new source IPs once the dict is full.
        # This bounds memory against sustained UDP source-IP spoofing
        # between eviction ticks (which run every 60s).
        if source_ip not in self._rate_window:
            if len(self._rate_window) >= self._rate_window_max_keys:
                return False
        window = self._rate_window.setdefault(source_ip, [])
        # Drop entries older than 60s.
        cutoff = now - 60
        pruned = [t for t in window if t > cutoff]
        if len(pruned) >= self._rate_limit_per_min:
            # Update in place to the pruned view so the dict doesn't
            # accumulate stale entries for IPs that hit the rate cap.
            self._rate_window[source_ip] = pruned
            return False
        pruned.append(now)
        self._rate_window[source_ip] = pruned
        return True

    def _evict_rate_window(self) -> None:
        """Drop expired entries from the rate window dict.

        Without this, a flood of spoofed source IPs (UDP — trivial to
        forge) would grow the dict without bound, exhausting memory.
        Called from the start() loop to bound the size.
        """
        now = time.time()
        cutoff = now - 60
        to_drop: list[str] = []
        for ip, window in list(self._rate_window.items()):
            # Walk window; an entry is "alive" if its newest timestamp
            # is within the cutoff. Use max() so we keep the freshest
            # state seen.
            if not window or max(window) <= cutoff:
                to_drop.append(ip)
            else:
                # Prune in-place so we don't accumulate stale entries
                # within a hot IP.
                self._rate_window[ip] = [t for t in window if t > cutoff]
        for ip in to_drop:
            # Re-check inside the lock-free critical section: if a
            # new entry arrived between the snapshot and the pop,
            # and it's still within the window, keep it.
            current = self._rate_window.get(ip)
            if not current or max(current) <= cutoff:
                self._rate_window.pop(ip, None)
