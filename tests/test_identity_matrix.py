from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from marketplace.identity import (
    IDENTITY_ACCESSORY_ONLY,
    IDENTITY_EXACT_CONFIRMED,
    IDENTITY_EXACT_STRONG,
    IDENTITY_FAMILY_ONLY,
    IDENTITY_PARTS_ONLY,
    identify_product,
)


class IdentityMatrixTests(unittest.TestCase):
    def test_gpu_fan_is_parts_or_accessory_not_exact(self):
        for title in ("RTX 4070 GPU Fan", "GPU Fan", "RTX 4070 fan", "graphics card fan"):
            ident = identify_product(title)
            self.assertIn(
                ident["identity_confidence"],
                {IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY},
                msg=title,
            )
            self.assertNotIn(
                ident["identity_confidence"],
                {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG},
                msg=title,
            )

    def test_rtx_4070_alone_still_exact(self):
        ident = identify_product("RTX 4070")
        self.assertIn(
            ident["identity_confidence"],
            {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG},
        )
        self.assertEqual(ident["candidate_model"], "RTX 4070")

    def test_rtx_4070_variants_still_exact(self):
        self.assertEqual(identify_product("RTX 4070 Ti SUPER")["candidate_model"], "RTX 4070 Ti SUPER")
        self.assertIn(
            identify_product("RTX 4070 Ti SUPER")["identity_confidence"],
            {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG},
        )

    def test_triple_fan_gpu_still_exact_not_parts(self):
        ident = identify_product("RTX 4070 Triple Fan OC")
        self.assertEqual(ident["candidate_model"], "RTX 4070")
        self.assertIn(
            ident["identity_confidence"],
            {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG},
        )

    def test_base_nintendo_switch_is_family_only(self):
        for title in ("Nintendo Switch", "Nintendo Switch console"):
            ident = identify_product(title)
            self.assertEqual(ident["identity_confidence"], IDENTITY_FAMILY_ONLY, msg=title)
            self.assertEqual(ident["candidate_product_family"], "switch-family", msg=title)
            self.assertEqual(ident["candidate_model"], "Nintendo Switch", msg=title)

    def test_switch_variants_still_exact(self):
        cases = {
            "Nintendo Switch OLED": "Nintendo Switch OLED",
            "Nintendo Switch Lite": "Nintendo Switch Lite",
            "Nintendo Switch 2": "Nintendo Switch 2",
        }
        for title, model in cases.items():
            ident = identify_product(title)
            self.assertEqual(ident["candidate_model"], model, msg=title)
            self.assertIn(
                ident["identity_confidence"],
                {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG},
                msg=title,
            )


if __name__ == "__main__":
    unittest.main()
