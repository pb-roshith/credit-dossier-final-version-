"""Authentication and authorization security checks."""

import unittest

from fastapi import HTTPException

from app.auth import (
    create_session,
    hash_password,
    require_credit_analyst,
    require_relationship_manager,
    validate_password_strength,
    verify_password,
)
from app.models import AuthSession
from test_case.support import DatabaseTestCase


class AuthenticationTests(DatabaseTestCase):
    def test_password_hashing_and_verification(self) -> None:
        encoded = hash_password("Correct-Horse-42!")

        self.assertNotIn("Correct-Horse-42!", encoded)
        self.assertTrue(verify_password("Correct-Horse-42!", encoded))
        self.assertFalse(verify_password("Wrong-Horse-42!", encoded))

    def test_password_policy_rejects_weak_and_user_id_passwords(self) -> None:
        invalid_passwords = (
            "short",
            "alllowercase123!",
            "ALLUPPERCASE123!",
            "NoNumberHere!",
            "NoSpecialCharacter42",
            "manager-Strong-42!",
        )
        for password in invalid_passwords:
            with self.subTest(password=password):
                with self.assertRaises(ValueError):
                    validate_password_strength(password, "manager")

        validate_password_strength("Strong-Unrelated-42!", "manager")

    def test_session_is_stored_as_a_hash(self) -> None:
        user = self.create_user()
        raw_token, session = create_session(self.db, user)

        stored = self.db.query(AuthSession).filter_by(id=session.id).one()
        self.assertNotEqual(raw_token, stored.token_hash)
        self.assertEqual(len(stored.token_hash), 64)

    def test_role_guards_enforce_workflow_permissions(self) -> None:
        manager = self.create_user()
        analyst = self.create_user("test.analyst", "credit_analyst")

        self.assertIs(require_relationship_manager(manager), manager)
        self.assertIs(require_credit_analyst(analyst), analyst)
        with self.assertRaises(HTTPException) as manager_error:
            require_relationship_manager(analyst)
        with self.assertRaises(HTTPException) as analyst_error:
            require_credit_analyst(manager)
        self.assertEqual(manager_error.exception.status_code, 403)
        self.assertEqual(analyst_error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

