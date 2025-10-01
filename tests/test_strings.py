import re
import unicodedata
import unittest


def normalize_str(s):
    # Normalize accents (e.g., é → e)
    s = unicodedata.normalize("NFD", s)  # noqa: F821
    # Removing diacritical marks (accents) from characters. 'Mn' → Nonspacing Mark.
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Convert to lowercase
    return s.lower()


def relaxed_equal(str1: str, str2: str) -> bool:
    # Remove all non-letter characters (keep only a-zA-Z)
    str1 = re.sub(r"[^A-Za-z]", "", str1)
    str2 = re.sub(r"[^A-Za-z]", "", str2)
    return normalize_str(str1) == normalize_str(str2)


class TestNormalizeStr(unittest.TestCase):
    def test(self):  # test method names begin with 'test'
        self.assertEqual(normalize_str("à"), "a")
        self.assertEqual(normalize_str("è"), "e")
        self.assertEqual(normalize_str("È"), "e")
        self.assertEqual(normalize_str("é"), "e")
        self.assertEqual(normalize_str("ì"), "i")
        self.assertEqual(normalize_str("ò"), "o")
        self.assertEqual(normalize_str("ù"), "u")
        self.assertEqual(normalize_str(" "), " ")
        self.assertEqual(normalize_str("Città"), "citta")
        self.assertEqual(normalize_str("coSì"), "cosi")
        self.assertEqual(normalize_str("résumé"), "resume")
        self.assertEqual(normalize_str("più"), "piu")
        self.assertEqual(
            normalize_str("Tu proverai sì come sa di sale lo pane altrui"),
            "tu proverai si come sa di sale lo pane altrui",
        )
        self.assertEqual(
            normalize_str("Come si può essere immortali e ugualmente morire?"),
            "come si puo essere immortali e ugualmente morire?",
        )
        self.assertEqual(
            normalize_str(
                "Molti grandi uomini erano ancora attivi a novant'anni! E sapete "
                "perché erano rimasti giovani? Perché avevano ancora dei sogni da realizzare!"
            ),
            "molti grandi uomini erano ancora attivi a novant'anni! e sapete "
            "perche erano rimasti giovani? perche avevano ancora dei sogni da realizzare!",
        )
        self.assertEqual(
            len(
                "Molti grandi uomini erano ancora attivi a novant'anni! E sapete perché erano rimasti giovani? Perché avevano ancora dei sogni da realizzare!"
            ),
            len(
                normalize_str(
                    "Molti grandi uomini erano ancora attivi a novant'anni! E sapete perché erano rimasti giovani? Perché avevano ancora dei sogni da realizzare!"
                )
            ),
        )
        self.assertEqual(
            normalize_str("Dove non c'è legge, non c'è nemmeno trasgressione"),
            "dove non c'e legge, non c'e nemmeno trasgressione",
        )
        self.assertEqual(
            len("Dove non c'è legge, non c'è nemmeno trasgressione"),
            len(normalize_str("Dove non c'è legge, non c'è nemmeno trasgressione")),
        )


if __name__ == "__main__":
    unittest.main()
