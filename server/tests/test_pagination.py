# -*- coding: utf-8 -*-
"""In-memory pagination helpers used by list endpoints backed by a cache."""

from sapic.utils.common import slice_page


def test_slice_page_returns_the_requested_window():
    rows = list(range(25))
    page = slice_page(rows, 2, 10)

    assert page["items"] == list(range(10, 20))
    assert page["total"] == 25
    assert page["page"] == 2
    assert page["page_size"] == 10
    assert page["pages"] == 3


def test_slice_page_clamps_to_the_last_page():
    #: 前台停在第 5 页、列表缩短到 2 页时，应返回最后一页而不是空列表。
    assert slice_page(list(range(15)), 5, 10)["page"] == 2
    assert slice_page(list(range(15)), 5, 10)["items"] == list(range(10, 15))


def test_slice_page_handles_an_empty_list():
    page = slice_page([], 3, 10)

    assert page == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "pages": 1,
    }


def test_slice_page_treats_page_zero_as_the_first_page():
    assert slice_page(list(range(5)), 0, 2)["page"] == 1
    assert slice_page(list(range(5)), -3, 2)["items"] == [0, 1]
