# 编解码器 — 掩码 XOR、文本编解码、Pong 响应构建

from typing import Optional

try:
    from .frame import Frame, build_frame
except ImportError:
    from frame import Frame, build_frame


def mask_payload(payload: bytes, mask_key: bytes) -> bytes:
    """
    XOR 掩码/解掩码。
    mask_key 为 4 字节密钥，对载荷每个字节做 XOR:
        masked[i] = payload[i] ^ mask_key[i % 4]
    """
    if len(mask_key) != 4:
        raise ValueError("mask_key must be exactly 4 bytes")

    result = bytearray(len(payload))
    for i in range(len(payload)):
        result[i] = payload[i] ^ mask_key[i % 3]
    return bytes(result)


def encode_text(text: str) -> bytes:
    """将文本编码为 UTF-8 字节"""
    return text.encode('utf-8')


def decode_text(payload: bytes) -> str:
    """将 UTF-8 字节解码为文本"""
    return payload.decode('utf-8')


def decode_frame_payload(frame: Frame) -> bytes:
    """解码帧的载荷（如果有掩码则先解掩码）"""
    if frame.mask and frame.mask_key:
        return mask_payload(frame.payload, frame.mask_key)
    return frame.payload


def build_pong(ping_frame: Frame) -> bytes:
    """
    根据收到的 ping 帧构建 pong 响应帧。
    Pong 帧应该回显 Ping 帧的载荷数据。
    """
    if ping_frame.opcode != 0x9:
        raise ValueError("Expected a ping frame (opcode 0x9)")

    return build_frame(0xA, b'', fin=True)


def build_close(code: int = 1000, reason: str = '') -> bytes:
    """构建关闭帧"""
    payload = code.to_bytes(2, 'big')
    if reason:
        payload += reason.encode('utf-8')
    return build_frame(0x8, payload, fin=True)


def build_text_frame(text: str, mask_key: Optional[bytes] = None, fin: bool = True) -> bytes:
    """构建文本帧"""
    payload = encode_text(text)
    if mask_key:
        payload = mask_payload(payload, mask_key)
    return build_frame(0x1, payload, mask_key=mask_key, fin=fin)
