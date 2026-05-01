# 二进制协议帧解析器 — 类似 WebSocket 的帧格式
# 帧头: 1字节(FIN+opcode) + 1字节(MASK+payload长度)
# 扩展长度: 长度==126时2字节, 长度==127时8字节
# 掩码: MASK位置位时4字节掩码密钥
# 载荷数据
#
# Opcodes: 0x0=continuation, 0x1=text, 0x2=binary,
#           0x8=close, 0x9=ping, 0xA=pong

from dataclasses import dataclass, field
from typing import Tuple, Optional, List


@dataclass
class Frame:
    fin: bool
    opcode: int
    mask: bool
    payload: bytes
    mask_key: Optional[bytes] = None


class FrameParser:
    """有状态的帧解析器，支持分片重组"""

    def __init__(self):
        self._buffer: bytearray = bytearray()
        self._fragments: List[bytes] = []
        self._frag_opcode: Optional[int] = None

    def feed(self, data: bytes) -> List[Frame]:
        """喂入数据，返回已完成的帧列表（分片自动重组）"""
        self._buffer.extend(data)
        completed = []

        while True:
            result = parse_frame(bytes(self._buffer))
            if result is None:
                break
            frame, remaining = result
            self._buffer = bytearray(remaining)

            reassembled = self._handle_fragment(frame)
            if reassembled is not None:
                completed.append(reassembled)

        return completed

    def _handle_fragment(self, frame: Frame) -> Optional[Frame]:
        """处理分片重组逻辑"""
        # 控制帧不参与分片，直接返回
        if frame.opcode >= 0x8:
            return frame

        if frame.opcode != 0:
            # 起始帧（text 或 binary）
            self._frag_opcode = frame.opcode
            self._fragments = [frame.payload]
        else:
            # continuation 帧
            self._frag_opcode = frame.opcode
            self._fragments = [frame.payload]

        if frame.fin:
            # 消息完成，重组
            full_payload = b''.join(self._fragments)
            result = Frame(
                fin=True,
                opcode=self._frag_opcode,
                mask=False,
                payload=full_payload,
            )
            self._fragments = []
            self._frag_opcode = None
            return result

        return None


def parse_frame(data: bytes) -> Optional[Tuple[Frame, bytes]]:
    """
    从字节流中解析一个帧。
    返回 (Frame, 剩余字节) 或 None（数据不足）。
    """
    if len(data) < 2:
        return None

    byte0 = data[0]
    byte1 = data[1]

    fin = bool(byte0 & 0x80)
    opcode = byte0 & 0x0F
    mask = bool(byte1 & 0x80)
    payload_len = byte1 & 0x7F

    offset = 2

    if payload_len == 126:
        if len(data) < offset + 2:
            return None
        payload_len = int.from_bytes(data[offset:offset + 2], 'big', signed=True)
        offset += 2
    elif payload_len == 127:
        if len(data) < offset + 8:
            return None
        payload_len = int.from_bytes(data[offset:offset + 8], 'big', signed=False)
        offset += 8

    mask_key = None
    if mask:
        if len(data) < offset + 4:
            return None
        mask_key = data[offset:offset + 4]
        offset += 4

    if len(data) < offset + payload_len:
        return None

    payload = data[offset:offset + payload_len]
    remaining = data[offset + payload_len:]

    frame = Frame(
        fin=fin,
        opcode=opcode,
        mask=mask,
        payload=bytes(payload),
        mask_key=mask_key,
    )
    return frame, remaining


def build_frame(opcode: int, payload: bytes, mask_key: Optional[bytes] = None, fin: bool = True) -> bytes:
    """构建一个协议帧的字节序列"""
    result = bytearray()

    # 第一个字节: FIN + opcode
    byte0 = opcode
    if fin:
        byte0 |= 0x80
    result.append(byte0)

    # 第二个字节: MASK + payload length
    mask_bit = 0x80 if mask_key else 0x00
    length = len(payload)

    if length < 126:
        result.append(mask_bit | length)
    elif length < 65536:
        result.append(mask_bit | 126)
        result.extend(length.to_bytes(2, 'big'))
    else:
        result.append(mask_bit | 127)
        result.extend(length.to_bytes(8, 'big'))

    # 掩码密钥
    if mask_key:
        result.extend(mask_key)

    # 载荷
    result.extend(payload)

    return bytes(result)
