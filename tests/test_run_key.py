import base64

import pytest

from unoq_lorenz.run_key import load_or_create_run_key


def test_generated_run_key_is_fresh_private_and_exclusive(tmp_path):
    first = load_or_create_run_key("run01", secret_dir=tmp_path)
    assert len(first.key) == 32
    assert first.origin == "generated_private_file"
    assert first.private_path is not None and first.private_path.read_bytes() == first.key
    with pytest.raises(FileExistsError):
        load_or_create_run_key("run01", secret_dir=tmp_path)


def test_environment_key_is_decoded_without_writing(tmp_path):
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    material = load_or_create_run_key(
        "run02", encoded_key=encoded, secret_dir=tmp_path
    )
    assert material.key == bytes(range(32))
    assert material.private_path is None
    assert not list(tmp_path.glob("*"))
