import pytest

from unoq_lorenz.nonce import NonceSequence


def test_allocate_returns_counter_and_96_bit_nonce():
    sequence = NonceSequence(b"PREFIX01", start=7)
    first = sequence.allocate()
    second = sequence.allocate()
    assert first.counter == 7
    assert first.nonce == b"PREFIX01" + (7).to_bytes(4, "big")
    assert second.counter == 8
    assert second.nonce == b"PREFIX01" + (8).to_bytes(4, "big")
    assert len(first.nonce) == 12
    assert sequence.next_counter == 9


def test_default_prefix_is_random_64_bit_value():
    first = NonceSequence()
    second = NonceSequence()
    assert len(first.prefix) == 8
    assert len(second.prefix) == 8
    assert first.prefix != second.prefix


def test_uint32_counter_emits_last_nonce_then_fails_closed():
    sequence = NonceSequence(b"OVERFLOW", start=2**32 - 1)
    allocation = sequence.allocate()
    assert allocation.counter == 2**32 - 1
    assert allocation.nonce[-4:] == b"\xff\xff\xff\xff"
    with pytest.raises(OverflowError, match="exhausted"):
        sequence.allocate()


@pytest.mark.parametrize("prefix", [b"short", b"ninebytes"])
def test_prefix_must_be_exactly_64_bits(prefix):
    with pytest.raises(ValueError, match="eight bytes"):
        NonceSequence(prefix)


@pytest.mark.parametrize("start", [-1, 2**32])
def test_counter_start_must_be_uint32(start):
    with pytest.raises(ValueError, match="uint32"):
        NonceSequence(b"PREFIX01", start=start)


def test_counter_start_rejects_boolean_even_though_bool_is_an_int_subclass():
    with pytest.raises(TypeError, match="integer"):
        NonceSequence(b"PREFIX01", start=True)
