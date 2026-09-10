import unittest

from integra_core.identity import CollisionDecision, derive_imported_id, resolve_collision


HASH_A = "a" * 64
HASH_B = "b" * 64


class IdentityTests(unittest.TestCase):
    def test_imported_id_is_deterministic_and_path_independent(self):
        first = derive_imported_id("artifact", "seminartext", "native-1", HASH_A)
        second = derive_imported_id("artifact", "seminartext", "native-1", HASH_A)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("urn:integra:artifact:"))

    def test_revision_change_changes_imported_id(self):
        first = derive_imported_id("artifact", "videotext", "native-1", HASH_A)
        second = derive_imported_id("artifact", "videotext", "native-1", HASH_B)
        self.assertNotEqual(first, second)

    def test_same_id_different_hash_is_hard_conflict(self):
        decision = resolve_collision("id-1", "id-1", HASH_A, HASH_B)
        self.assertEqual(decision, CollisionDecision.HARD_CONFLICT)

    def test_different_id_same_hash_requires_explicit_alias(self):
        decision = resolve_collision("id-1", "id-2", HASH_A, HASH_A)
        self.assertEqual(decision, CollisionDecision.REGISTER_ALIAS)


if __name__ == "__main__":
    unittest.main()
