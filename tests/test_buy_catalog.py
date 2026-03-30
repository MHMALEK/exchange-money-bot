"""Tests for buyer catalog pagination math and buy-flow callback regex (EUR/USD)."""

from __future__ import annotations

import math
import re
import unittest


_BUY_CCY = r"(EUR|USD)"
BUY_FLOW_PATTERN = rf"^buy:(choose|ccy:{_BUY_CCY}|cat:{_BUY_CCY}:\d+)$"


class TestBuyCallbackRegex(unittest.TestCase):
    def test_all_currency_buttons_match(self) -> None:
        for ccy in ("EUR", "USD"):
            with self.subTest(ccy=ccy):
                data = f"buy:ccy:{ccy}"
                self.assertIsNotNone(re.match(BUY_FLOW_PATTERN, data), data)
                self.assertIsNotNone(re.fullmatch(rf"buy:ccy:{_BUY_CCY}", data), data)

    def test_pagination_callbacks(self) -> None:
        for ccy, page in [("USD", 3), ("EUR", 99)]:
            data = f"buy:cat:{ccy}:{page}"
            self.assertIsNotNone(re.match(BUY_FLOW_PATTERN, data), data)
            m = re.fullmatch(rf"buy:cat:{_BUY_CCY}:(\d+)", data)
            self.assertIsNotNone(m)
            assert m is not None
            self.assertEqual(m.group(1), ccy)
            self.assertEqual(int(m.group(2)), page)

    def test_removed_currency_not_matched(self) -> None:
        self.assertIsNone(re.fullmatch(rf"buy:ccy:{_BUY_CCY}", "buy:ccy:USDT"))
        self.assertIsNone(re.match(BUY_FLOW_PATTERN, "buy:ccy:USDT"))


class TestPaginationMath(unittest.TestCase):
    def _clamp_page(self, page: int, total_pages: int) -> int:
        return max(0, min(page, total_pages - 1))

    def _offset(self, page: int, page_size: int) -> int:
        return page * page_size

    def test_total_pages(self) -> None:
        ps = 20
        self.assertEqual(max(1, math.ceil(0 / ps)), 1)  # UI short-circuits; this is formula-only
        self.assertEqual(max(1, math.ceil(3 / ps)), 1)
        self.assertEqual(max(1, math.ceil(20 / ps)), 1)
        self.assertEqual(max(1, math.ceil(21 / ps)), 2)
        self.assertEqual(max(1, math.ceil(40 / ps)), 2)

    def test_offsets_and_clamp(self) -> None:
        ps = 20
        total = 25
        total_pages = max(1, math.ceil(total / ps))
        self.assertEqual(total_pages, 2)
        self.assertEqual(self._offset(0, ps), 0)
        self.assertEqual(self._offset(1, ps), 20)
        self.assertEqual(self._clamp_page(0, total_pages), 0)
        self.assertEqual(self._clamp_page(1, total_pages), 1)
        self.assertEqual(self._clamp_page(99, total_pages), 1)


if __name__ == "__main__":
    unittest.main()
