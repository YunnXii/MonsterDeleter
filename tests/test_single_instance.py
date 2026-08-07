from pathlib import Path

from app.single_instance import decode_command, encode_command, make_command


def test_activate_command_round_trip() -> None:
    command = make_command()
    payload = encode_command(command)

    assert decode_command(payload.strip()) == command


def test_target_command_round_trip_keeps_unicode_path() -> None:
    command = make_command(Path(r"D:\桌面\倒霉文件.docx"))
    payload = encode_command(command)

    assert decode_command(payload.strip()) == command


def test_invalid_command_is_rejected() -> None:
    assert decode_command(b"not-json") is None
    assert decode_command(b'{"version":999,"type":"activate"}') is None
    assert decode_command(b'{"version":1,"type":"target"}') is None
