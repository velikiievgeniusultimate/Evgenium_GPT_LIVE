import unittest

from egl.phrases import normalize_phrase, phrase_matches


class PhraseTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_phrase("Евгениум, СТОП."), "евгениум стоп")

    def test_alias_suffix(self):
        self.assertTrue(phrase_matches("ну евгений слушай", ["евгений слушай"]))
        self.assertFalse(phrase_matches("евгений привет", ["евгений слушай"]))


if __name__ == "__main__":
    unittest.main()
