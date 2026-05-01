# protocol_parser_test.py — 协议解析器测试
# 不要修改此文件

import struct
import pytest

# 为了支持直接运行和 pytest，使用两种导入方式
try:
    from .frame import Frame, FrameParser, parse_frame, build_frame
    from .codec import mask_payload, encode_text, decode_text, decode_frame_payload, build_pong, build_close, build_text_frame
    from .session import Session, State
except ImportError:
    from frame import Frame, FrameParser, parse_frame, build_frame
    from codec import mask_payload, encode_text, decode_text, decode_frame_payload, build_pong, build_close, build_text_frame
    from session import Session, State


# ============================================================
# 辅助函数
# ============================================================

def _make_frame_bytes(fin: bool, opcode: int, payload: bytes,
                      mask_key: bytes = None) -> bytes:
    """手动构造帧的原始字节（不依赖 build_frame，用于独立验证解析器）"""
    buf = bytearray()
    b0 = opcode
    if fin:
        b0 |= 0x80
    buf.append(b0)

    mask_bit = 0x80 if mask_key else 0x00
    length = len(payload)
    if length < 126:
        buf.append(mask_bit | length)
    elif length < 65536:
        buf.append(mask_bit | 126)
        buf.extend(struct.pack('!H', length))
    else:
        buf.append(mask_bit | 127)
        buf.extend(struct.pack('!Q', length))

    if mask_key:
        buf.extend(mask_key)

    if mask_key:
        masked = bytearray(length)
        for i in range(length):
            masked[i] = payload[i] ^ mask_key[i % 4]
        buf.extend(masked)
    else:
        buf.extend(payload)

    return bytes(buf)


# ============================================================
# frame.py 测试
# ============================================================

class TestParseFrame:
    """帧解析测试"""

    def test_parse_small_text_frame(self):
        """小文本帧解析"""
        payload = b'Hello'
        raw = _make_frame_bytes(fin=True, opcode=0x1, payload=payload)
        result = parse_frame(raw)
        assert result is not None
        frame, remaining = result
        assert frame.fin is True
        assert frame.opcode == 0x1
        assert frame.mask is False
        assert frame.payload == payload
        assert remaining == b''

    def test_parse_masked_frame(self):
        """掩码帧解析"""
        payload = b'World'
        mask_key = b'\x37\x42\x59\x6a'
        raw = _make_frame_bytes(fin=True, opcode=0x1, payload=payload, mask_key=mask_key)
        result = parse_frame(raw)
        assert result is not None
        frame, remaining = result
        assert frame.fin is True
        assert frame.opcode == 0x1
        assert frame.mask is True
        assert frame.mask_key == mask_key
        # 载荷应该是掩码后的数据（parse_frame 不做解掩码）
        assert len(frame.payload) == len(payload)

    def test_parse_extended_length_126(self):
        """BUG 1 测试：2字节扩展长度 — 200字节载荷"""
        payload = bytes(range(256)) * 1 + bytes(range(200 - 256)) if 200 > 256 else bytes(range(200))
        payload = bytes([i % 256 for i in range(200)])
        raw = _make_frame_bytes(fin=True, opcode=0x2, payload=payload)
        result = parse_frame(raw)
        assert result is not None
        frame, remaining = result
        assert frame.payload == payload
        assert len(frame.payload) == 200

    def test_parse_extended_length_large(self):
        """BUG 1 核心测试：长度 > 32767 的帧（signed=True 会导致负数）"""
        # 构造 40000 字节载荷 — 这个长度使用 2 字节扩展长度
        # 40000 > 32767，如果 signed=True 会被解析为 -25536
        payload = b'\xAB' * 40000
        raw = _make_frame_bytes(fin=True, opcode=0x2, payload=payload)
        result = parse_frame(raw)
        assert result is not None
        frame, remaining = result
        assert len(frame.payload) == 40000
        assert frame.payload == payload

    def test_parse_8byte_extended_length(self):
        """8字节扩展长度帧（长度 == 127 编码）"""
        payload = b'\x00' * 70000
        raw = _make_frame_bytes(fin=True, opcode=0x2, payload=payload)
        result = parse_frame(raw)
        assert result is not None
        frame, remaining = result
        assert len(frame.payload) == 70000

    def test_parse_incomplete_data(self):
        """数据不完整返回 None"""
        assert parse_frame(b'') is None
        assert parse_frame(b'\x81') is None
        # 声称 126 字节但只有头
        assert parse_frame(b'\x81\x7e') is None

    def test_parse_multiple_frames(self):
        """连续两帧的解析"""
        f1 = _make_frame_bytes(fin=True, opcode=0x1, payload=b'one')
        f2 = _make_frame_bytes(fin=True, opcode=0x1, payload=b'two')
        data = f1 + f2
        result1 = parse_frame(data)
        assert result1 is not None
        frame1, rest = result1
        assert frame1.payload == b'one'
        result2 = parse_frame(rest)
        assert result2 is not None
        frame2, rest2 = result2
        assert frame2.payload == b'two'
        assert rest2 == b''


class TestBuildFrame:
    """帧构建测试"""

    def test_build_small_frame(self):
        """构建小帧并解析回来"""
        raw = build_frame(0x1, b'test')
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.fin is True
        assert frame.opcode == 0x1
        assert frame.payload == b'test'

    def test_build_frame_with_mask(self):
        """构建带掩码的帧"""
        mask_key = b'\x01\x02\x03\x04'
        raw = build_frame(0x1, b'data', mask_key=mask_key, fin=True)
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.mask is True
        assert frame.mask_key == mask_key

    def test_build_frame_extended_length(self):
        """构建使用扩展长度的帧"""
        payload = b'\xff' * 300
        raw = build_frame(0x2, payload)
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.payload == payload

    def test_build_continuation_frame(self):
        """构建 continuation 帧（fin=False）"""
        raw = build_frame(0x0, b'cont', fin=False)
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.fin is False
        assert frame.opcode == 0x0


# ============================================================
# codec.py 测试
# ============================================================

class TestMaskPayload:
    """掩码编解码测试"""

    def test_mask_unmask_roundtrip(self):
        """BUG 3 核心测试：掩码后再解掩码得到原文"""
        key = b'\xAA\xBB\xCC\xDD'
        original = b'Hello, Protocol!'
        masked = mask_payload(original, key)
        # 掩码是自反操作，再做一次就还原
        unmasked = mask_payload(masked, key)
        assert unmasked == original

    def test_mask_single_byte(self):
        """单字节掩码"""
        key = b'\x00\x00\x00\xFF'
        result = mask_payload(b'\x42', key)
        # 0x42 ^ 0x00 = 0x42
        assert result == b'\x42'

    def test_mask_four_bytes(self):
        """BUG 3 验证：正好 4 字节时每个字节对应 key 的一位"""
        key = b'\x01\x02\x03\x04'
        data = b'\x10\x20\x30\x40'
        result = mask_payload(data, key)
        assert result == bytes([0x10 ^ 0x01, 0x20 ^ 0x02, 0x30 ^ 0x03, 0x40 ^ 0x04])

    def test_mask_five_bytes(self):
        """BUG 3 验证：第5字节应该用 key[0]，不是 key[1]"""
        key = b'\x01\x02\x03\x04'
        data = b'\x10\x20\x30\x40\x50'
        result = mask_payload(data, key)
        expected = bytes([
            0x10 ^ 0x01,  # i=0, key[0]
            0x20 ^ 0x02,  # i=1, key[1]
            0x30 ^ 0x03,  # i=2, key[2]
            0x40 ^ 0x04,  # i=3, key[3]
            0x50 ^ 0x01,  # i=4, key[4 % 4 = 0]  (BUG: i % 3 = 1 → key[1])
        ])
        assert result == expected

    def test_mask_long_payload(self):
        """长载荷掩码正确性"""
        key = b'\xDE\xAD\xBE\xEF'
        data = bytes(range(256)) * 4  # 1024 字节
        masked = mask_payload(data, key)
        unmasked = mask_payload(masked, key)
        assert unmasked == data

    def test_mask_invalid_key_length(self):
        """密钥长度不为4时抛异常"""
        with pytest.raises(ValueError):
            mask_payload(b'test', b'\x01\x02\x03')


class TestTextCodec:
    """文本编解码测试"""

    def test_encode_decode_ascii(self):
        assert decode_text(encode_text("hello")) == "hello"

    def test_encode_decode_unicode(self):
        text = "你好世界 🌍"
        assert decode_text(encode_text(text)) == text

    def test_decode_frame_payload_unmasked(self):
        """无掩码帧的载荷解码"""
        frame = Frame(fin=True, opcode=0x1, mask=False, payload=b'plain')
        assert decode_frame_payload(frame) == b'plain'

    def test_decode_frame_payload_masked(self):
        """掩码帧的载荷解码"""
        key = b'\x01\x02\x03\x04'
        original = b'secret'
        masked = mask_payload(original, key)
        frame = Frame(fin=True, opcode=0x1, mask=True, payload=masked, mask_key=key)
        assert decode_frame_payload(frame) == original


class TestBuildPong:
    """Pong 构建测试"""

    def test_pong_echoes_payload(self):
        """BUG 4 核心测试：pong 必须回显 ping 的 payload"""
        ping_payload = b'ping-data-123'
        ping_frame = Frame(fin=True, opcode=0x9, mask=False, payload=ping_payload)
        pong_bytes = build_pong(ping_frame)

        result = parse_frame(pong_bytes)
        assert result is not None
        pong_frame, _ = result
        assert pong_frame.opcode == 0xA
        assert pong_frame.payload == ping_payload

    def test_pong_empty_payload(self):
        """空载荷 ping 的 pong 也应该是空载荷"""
        ping_frame = Frame(fin=True, opcode=0x9, mask=False, payload=b'')
        pong_bytes = build_pong(ping_frame)
        result = parse_frame(pong_bytes)
        assert result is not None
        pong_frame, _ = result
        assert pong_frame.opcode == 0xA
        assert pong_frame.payload == b''

    def test_pong_wrong_opcode_raises(self):
        """非 ping 帧调用 build_pong 应该报错"""
        text_frame = Frame(fin=True, opcode=0x1, mask=False, payload=b'text')
        with pytest.raises(ValueError):
            build_pong(text_frame)


class TestBuildClose:
    """关闭帧构建测试"""

    def test_build_close_default(self):
        raw = build_close()
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.opcode == 0x8
        code = int.from_bytes(frame.payload[:2], 'big')
        assert code == 1000

    def test_build_close_with_reason(self):
        raw = build_close(1001, "going away")
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        code = int.from_bytes(frame.payload[:2], 'big')
        reason = frame.payload[2:].decode('utf-8')
        assert code == 1001
        assert reason == "going away"


# ============================================================
# FrameParser 分片重组测试
# ============================================================

class TestFrameParserFragmentation:
    """BUG 2 核心测试：分片帧重组"""

    def test_single_unfragmented_message(self):
        """单个完整帧，不分片"""
        parser = FrameParser()
        raw = _make_frame_bytes(fin=True, opcode=0x1, payload=b'hello')
        frames = parser.feed(raw)
        assert len(frames) == 1
        assert frames[0].payload == b'hello'
        assert frames[0].opcode == 0x1

    def test_two_fragment_reassembly(self):
        """BUG 2 核心：两片重组 — 第一片 FIN=0 opcode=text，第二片 FIN=1 opcode=continuation"""
        parser = FrameParser()

        # 第一片: FIN=0, opcode=0x1 (text), payload="hel"
        frag1 = _make_frame_bytes(fin=False, opcode=0x1, payload=b'hel')
        # 第二片: FIN=1, opcode=0x0 (continuation), payload="lo"
        frag2 = _make_frame_bytes(fin=True, opcode=0x0, payload=b'lo')

        result1 = parser.feed(frag1)
        assert len(result1) == 0  # 还没收完

        result2 = parser.feed(frag2)
        assert len(result2) == 1
        assert result2[0].payload == b'hello'
        assert result2[0].opcode == 0x1  # 最终帧应该保留起始帧的 opcode

    def test_three_fragment_reassembly(self):
        """三片重组"""
        parser = FrameParser()

        frag1 = _make_frame_bytes(fin=False, opcode=0x2, payload=b'AA')
        frag2 = _make_frame_bytes(fin=False, opcode=0x0, payload=b'BB')
        frag3 = _make_frame_bytes(fin=True, opcode=0x0, payload=b'CC')

        assert parser.feed(frag1) == []
        assert parser.feed(frag2) == []

        result = parser.feed(frag3)
        assert len(result) == 1
        assert result[0].payload == b'AABBCC'
        assert result[0].opcode == 0x2

    def test_control_frame_interleaved(self):
        """控制帧可以插在分片之间"""
        parser = FrameParser()

        frag1 = _make_frame_bytes(fin=False, opcode=0x1, payload=b'part1')
        ping = _make_frame_bytes(fin=True, opcode=0x9, payload=b'ping!')
        frag2 = _make_frame_bytes(fin=True, opcode=0x0, payload=b'part2')

        result1 = parser.feed(frag1)
        assert len(result1) == 0

        result2 = parser.feed(ping)
        assert len(result2) == 1
        assert result2[0].opcode == 0x9  # ping 立即返回

        result3 = parser.feed(frag2)
        assert len(result3) == 1
        assert result3[0].payload == b'part1part2'

    def test_two_consecutive_messages(self):
        """两个独立的完整消息"""
        parser = FrameParser()
        data = (_make_frame_bytes(fin=True, opcode=0x1, payload=b'msg1') +
                _make_frame_bytes(fin=True, opcode=0x1, payload=b'msg2'))
        frames = parser.feed(data)
        assert len(frames) == 2
        assert frames[0].payload == b'msg1'
        assert frames[1].payload == b'msg2'


# ============================================================
# session.py 测试
# ============================================================

class TestSession:
    """会话管理测试"""

    def test_session_lifecycle(self):
        """基本生命周期：CONNECTING -> OPEN -> send/receive -> CLOSED"""
        session = Session()
        assert session.state == State.CONNECTING

        session.open()
        assert session.state == State.OPEN
        assert session.is_open

    def test_send_text(self):
        """发送文本消息"""
        session = Session()
        session.open()
        frame_data = session.send_text("Hello")
        # 验证帧数据可解析
        result = parse_frame(frame_data)
        assert result is not None
        frame, _ = result
        assert frame.opcode == 0x1
        assert frame.payload == b'Hello'

    def test_receive_text(self):
        """接收文本消息"""
        session = Session()
        session.open()
        raw = _make_frame_bytes(fin=True, opcode=0x1, payload=b'world')
        messages = session.receive(raw)
        assert messages == ['world']
        assert session.received_messages == ['world']

    def test_ping_pong_auto_response(self):
        """收到 Ping 自动回 Pong"""
        session = Session()
        session.open()
        ping_data = _make_frame_bytes(fin=True, opcode=0x9, payload=b'heartbeat')
        session.receive(ping_data)
        outbox = session.drain_outbox()
        assert len(outbox) == 1
        # 解析 pong 帧
        result = parse_frame(outbox[0])
        assert result is not None
        pong_frame, _ = result
        assert pong_frame.opcode == 0xA
        # BUG 4 在这里体现：pong 载荷应该等于 ping 载荷
        assert pong_frame.payload == b'heartbeat'

    def test_active_close(self):
        """主动关闭"""
        session = Session()
        session.open()
        session.send_close(1000, "bye")
        assert session.state == State.CLOSING
        assert session.close_code == 1000

        # 收到对方的关闭应答
        close_response = _make_frame_bytes(fin=True, opcode=0x8, payload=b'\x03\xe8')
        session.receive(close_response)
        assert session.state == State.CLOSED

    def test_passive_close_sends_response(self):
        """BUG 5 核心测试：被动关闭 — 收到对方的 close，应该回 close 应答"""
        session = Session()
        session.open()

        close_payload = b'\x03\xe8' + b'server shutdown'  # code=1000
        close_data = _make_frame_bytes(fin=True, opcode=0x8, payload=close_payload)
        session.receive(close_data)

        # 1) 应该发送了关闭响应帧
        outbox = session.drain_outbox()
        assert len(outbox) >= 1, "Should send close response frame"

        # 验证关闭响应帧
        result = parse_frame(outbox[-1])
        assert result is not None
        response_frame, _ = result
        assert response_frame.opcode == 0x8

        # 2) 状态应该最终变为 CLOSED
        assert session.state == State.CLOSED

        # 3) 关闭码应该被正确记录
        assert session.close_code == 1000
        assert session.close_reason == 'server shutdown'

    def test_passive_close_transitions_through_closing(self):
        """BUG 5 补充：被动关闭应该经过 CLOSING 中间状态（或直接 CLOSED 但必须发送响应）"""
        session = Session()
        session.open()

        close_data = _make_frame_bytes(fin=True, opcode=0x8, payload=b'\x03\xe9')  # 1001
        session.receive(close_data)

        # 确保有关闭响应
        outbox = session.drain_outbox()
        assert len(outbox) >= 1, "Must send close frame back"

        # 最终状态为 CLOSED
        assert session.state == State.CLOSED
        assert session.close_code == 1001

    def test_send_on_closed_raises(self):
        """关闭后不能发送"""
        session = Session()
        session.open()

        # 被动关闭 — 使连接进入 CLOSED
        close_data = _make_frame_bytes(fin=True, opcode=0x8, payload=b'\x03\xe8')
        session.receive(close_data)
        # drain to clear
        session.drain_outbox()

        with pytest.raises(RuntimeError):
            session.send_text("too late")

    def test_receive_on_closed_raises(self):
        """关闭后不能接收"""
        session = Session()
        session.open()
        close_data = _make_frame_bytes(fin=True, opcode=0x8, payload=b'\x03\xe8')
        session.receive(close_data)
        session.drain_outbox()

        with pytest.raises(RuntimeError):
            session.receive(b'\x00')

    def test_outbox_drains(self):
        """outbox drain 后清空"""
        session = Session()
        session.open()
        session.send_text("a")
        session.send_text("b")
        first = session.drain_outbox()
        assert len(first) == 2
        second = session.drain_outbox()
        assert len(second) == 0

    def test_receive_multiple_messages(self):
        """一次接收多条消息"""
        session = Session()
        session.open()
        data = (_make_frame_bytes(fin=True, opcode=0x1, payload=b'alpha') +
                _make_frame_bytes(fin=True, opcode=0x1, payload=b'beta'))
        messages = session.receive(data)
        assert messages == ['alpha', 'beta']


# ============================================================
# 综合集成测试
# ============================================================

class TestIntegration:
    """端到端集成测试"""

    def test_masked_text_roundtrip(self):
        """掩码文本帧完整流程：构建 -> 解析 -> 解掩码"""
        key = b'\x12\x34\x56\x78'
        text = "Integration test 集成测试"
        frame_bytes = build_text_frame(text, mask_key=key)

        result = parse_frame(frame_bytes)
        assert result is not None
        frame, _ = result

        payload = decode_frame_payload(frame)
        assert decode_text(payload) == text

    def test_large_frame_roundtrip(self):
        """大帧（>32767字节）完整流程"""
        payload = bytes([i % 256 for i in range(40000)])
        raw = build_frame(0x2, payload)
        result = parse_frame(raw)
        assert result is not None
        frame, _ = result
        assert frame.payload == payload

    def test_fragmented_session(self):
        """分片消息通过 Session 接收"""
        session = Session()
        session.open()

        frag1 = _make_frame_bytes(fin=False, opcode=0x1, payload=b'foo')
        frag2 = _make_frame_bytes(fin=True, opcode=0x0, payload=b'bar')

        msgs1 = session.receive(frag1)
        assert msgs1 == []

        msgs2 = session.receive(frag2)
        assert msgs2 == ['foobar']

    def test_full_conversation(self):
        """完整对话：打开 -> 收发消息 -> ping/pong -> 被动关闭"""
        session = Session()
        session.open()

        # 收到两条消息
        data = (_make_frame_bytes(fin=True, opcode=0x1, payload=b'hi') +
                _make_frame_bytes(fin=True, opcode=0x1, payload=b'there'))
        msgs = session.receive(data)
        assert msgs == ['hi', 'there']

        # 发送一条消息
        session.send_text("reply")
        outbox = session.drain_outbox()
        assert len(outbox) == 1

        # 收到 ping
        ping = _make_frame_bytes(fin=True, opcode=0x9, payload=b'keep-alive')
        session.receive(ping)
        pong_out = session.drain_outbox()
        assert len(pong_out) == 1
        pong_frame, _ = parse_frame(pong_out[0])
        assert pong_frame.payload == b'keep-alive'

        # 对方发起关闭
        close = _make_frame_bytes(fin=True, opcode=0x8, payload=b'\x03\xe8bye')
        session.receive(close)
        close_out = session.drain_outbox()
        assert len(close_out) >= 1  # 发送了关闭响应
        assert session.state == State.CLOSED
        assert session.close_code == 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
