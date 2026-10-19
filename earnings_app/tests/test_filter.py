"""Tests for kurus_tl and kurus_to_tl_input template filters."""
import pytest
from earnings_app.templatetags.earnings_filters import kurus_tl, kurus_to_tl_input


def test_kurus_tl_basic():
    assert kurus_tl(83300)  == '833 ₺'
    assert kurus_tl(166600) == '1.666 ₺'
    assert kurus_tl(250000) == '2.500 ₺'


def test_kurus_tl_floors_odd_kurus():
    # Stored values that are not multiples of 100 floor to whole TL
    assert kurus_tl(83333)  == '833 ₺'
    assert kurus_tl(166667) == '1.666 ₺'


def test_kurus_tl_zero():
    assert kurus_tl(0) == '0 ₺'


def test_kurus_tl_negative():
    assert kurus_tl(-5000) == '-50 ₺'


def test_kurus_tl_large():
    assert kurus_tl(31990000) == '319.900 ₺'


def test_kurus_tl_invalid_returns_value():
    assert kurus_tl(None) is None
    assert kurus_tl('abc') == 'abc'


def test_kurus_to_tl_input_basic():
    assert kurus_to_tl_input(250000) == '2500'
    assert kurus_to_tl_input(83300)  == '833'
    assert kurus_to_tl_input(0)      == '0'


def test_kurus_to_tl_input_floors_odd_kurus():
    assert kurus_to_tl_input(83333) == '833'


def test_kurus_to_tl_input_invalid():
    assert kurus_to_tl_input(None)  == '0'
    assert kurus_to_tl_input('bad') == '0'
