# 会话管理 — 连接状态机、收发消息、关闭握手

from enum import Enum
from typing import List, Optional, Callable

try:
    from .frame import Frame, FrameParser, parse_frame, build_frame
    from .codec import decode_frame_payload, decode_text, build_pong, build_close
except ImportError:
    from frame import Frame, FrameParser, parse_frame, build_frame
    from codec import decode_frame_payload, decode_text, build_pong, build_close


class State(Enum):
    CONNECTING = "CONNECTING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class Session:
    """协议会话，管理连接生命周期"""

    def __init__(self):
        self.state: State = State.CONNECTING
        self.parser: FrameParser = FrameParser()
        self._outbox: List[bytes] = []  # 待发送的帧字节
        self._messages: List[str] = []  # 已接收的完整文本消息
        self._close_code: Optional[int] = None
        self._close_reason: str = ''

    def open(self):
        """完成握手，进入 OPEN 状态"""
        if self.state != State.CONNECTING:
            raise RuntimeError(f"Cannot open: state is {self.state.value}")
        self.state = State.OPEN

    @property
    def is_open(self) -> bool:
        return self.state == State.OPEN

    @property
    def close_code(self) -> Optional[int]:
        return self._close_code

    @property
    def close_reason(self) -> str:
        return self._close_reason

    def receive(self, data: bytes) -> List[str]:
        """
        接收原始数据，返回已完成的文本消息列表。
        自动处理控制帧（ping/pong/close）。
        """
        if self.state == State.CLOSED:
            raise RuntimeError("Session is closed")

        messages = []
        frames = self.parser.feed(data)

        for frame in frames:
            payload = decode_frame_payload(frame)

            if frame.opcode == 0x1:
                # 文本帧
                text = decode_text(payload)
                messages.append(text)
                self._messages.append(text)

            elif frame.opcode == 0x2:
                # 二进制帧 — 当作 hex 字符串存储
                messages.append(payload.hex())

            elif frame.opcode == 0x9:
                # Ping — 自动回 Pong
                pong_data = build_pong(frame)
                self._outbox.append(pong_data)

            elif frame.opcode == 0xA:
                # Pong — 忽略
                pass

            elif frame.opcode == 0x8:
                # Close 帧
                self._handle_close(payload)

        return messages

    def send_text(self, text: str) -> bytes:
        """发送文本消息，返回构建的帧字节"""
        if self.state != State.OPEN:
            raise RuntimeError(f"Cannot send: state is {self.state.value}")
        payload = text.encode('utf-8')
        frame_data = build_frame(0x1, payload, fin=True)
        self._outbox.append(frame_data)
        return frame_data

    def send_close(self, code: int = 1000, reason: str = '') -> bytes:
        """主动发起关闭"""
        if self.state != State.OPEN:
            raise RuntimeError(f"Cannot close: state is {self.state.value}")
        self.state = State.CLOSING
        frame_data = build_close(code, reason)
        self._outbox.append(frame_data)
        self._close_code = code
        self._close_reason = reason
        return frame_data

    def _handle_close(self, payload: bytes):
        """处理收到的关闭帧"""
        # 解析关闭码和原因
        if len(payload) >= 2:
            self._close_code = int.from_bytes(payload[:2], 'big')
            self._close_reason = payload[2:].decode('utf-8', errors='replace')
        else:
            self._close_code = 1005  # No status code
            self._close_reason = ''

        if self.state == State.OPEN:
            self.state = State.CLOSED
        elif self.state == State.CLOSING:
            # 我们先发了关闭帧，现在收到对方的关闭应答
            self.state = State.CLOSED

    def drain_outbox(self) -> List[bytes]:
        """取出所有待发送的帧数据"""
        frames = list(self._outbox)
        self._outbox.clear()
        return frames

    @property
    def received_messages(self) -> List[str]:
        """所有已接收的文本消息"""
        return list(self._messages)
