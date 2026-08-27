import unittest
import logging
from datetime import timedelta

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth as auth
from app.audit import DatabaseAuditLogHandler, install_audit_middleware
from app.config import settings
from app.database import Base, get_db
from app.models.user import AuditLog, PasswordPolicyConfiguration, User
from app.routers.admin import router as admin_router
from app.routers.auth import router
from app.error_handlers import install_exception_handlers


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)


def override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(router)
app.include_router(admin_router)
app.dependency_overrides[get_db] = override_db
install_exception_handlers(app)
install_audit_middleware(app, TestingSession)


@app.get("/api/test/system-error")
def system_error_for_audit_test():
    raise RuntimeError("intentional audit test error")


client = TestClient(app)


def test_three_security_questions_protect_password_reset():
    original_iterations = auth.PBKDF2_ITERATIONS
    auth.PBKDF2_ITERATIONS = 1_000
    questions = settings.security_question_options[:3]
    questions[2] = "What is the title of my favorite book?"
    responses = [
        {"question": question, "answer": f"Answer {index}"}
        for index, question in enumerate(questions, start=1)
    ]
    try:
        registration = client.post(
            "/api/auth/register",
            json={
                "user_id": "recovery-test",
                "password": "StrongPassword1!",
                "confirm_password": "StrongPassword1!",
                "role": "credit_analyst",
                "security_questions": responses,
            },
        )
        assert registration.status_code == 201, registration.text

        # Password-recovery behavior is tested after the new account has passed
        # the administrator approval gate.
        db = TestingSession()
        try:
            registered_user = db.query(User).filter(User.user_id == "recovery-test").one()
            registered_user.is_approved = True
            db.commit()
        finally:
            db.close()

        lookup = client.post(
            "/api/auth/reset-password/questions", json={"user_id": "recovery-test"}
        )
        assert lookup.status_code == 200
        assert lookup.json()["questions"] == questions

        incorrect = [dict(item) for item in responses]
        incorrect[2]["answer"] = "Wrong answer"
        rejected = client.post(
            "/api/auth/reset-password",
            json={
                "user_id": "recovery-test",
                "security_questions": incorrect,
                "new_password": "DifferentPassword2!",
                "confirm_password": "DifferentPassword2!",
            },
        )
        assert rejected.status_code == 400

        reset = client.post(
            "/api/auth/reset-password",
            json={
                "user_id": "recovery-test",
                "security_questions": responses,
                "new_password": "DifferentPassword2!",
                "confirm_password": "DifferentPassword2!",
            },
        )
        assert reset.status_code == 200, reset.text
        assert client.post(
            "/api/auth/login",
            json={"user_id": "recovery-test", "password": "StrongPassword1!"},
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"user_id": "recovery-test", "password": "DifferentPassword2!"},
        ).status_code == 200

        replacement = [
            {"question": question, "answer": f"Replacement {index}"}
            for index, question in enumerate(settings.security_question_options[3:6], start=1)
        ]
        configured = client.put(
            "/api/auth/security-questions",
            json={
                "current_password": "DifferentPassword2!",
                "security_questions": replacement,
            },
        )
        assert configured.status_code == 200, configured.text
        replaced_lookup = client.post(
            "/api/auth/reset-password/questions", json={"user_id": "recovery-test"}
        )
        assert replaced_lookup.json()["questions"] == [item["question"] for item in replacement]

        failed_change = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "WrongCurrentPassword1!",
                "new_password": "FinalPassword3!",
                "confirm_password": "FinalPassword3!",
            },
        )
        assert failed_change.status_code == 400
        successful_change = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "DifferentPassword2!",
                "new_password": "FinalPassword3!",
                "confirm_password": "FinalPassword3!",
            },
        )
        assert successful_change.status_code == 200, successful_change.text

        db = TestingSession()
        try:
            events = (
                db.query(AuditLog)
                .filter(
                    AuditLog.user_id == "recovery-test",
                    AuditLog.event_type.in_(["reset_password", "change_password"]),
                )
                .order_by(AuditLog.occurred_at)
                .all()
            )
            assert [(event.event_type, event.status) for event in events] == [
                ("reset_password", "failure"),
                ("reset_password", "success"),
                ("change_password", "failure"),
                ("change_password", "success"),
            ]
            assert all(event.occurred_at is not None for event in events)
            assert all(event.source_ip for event in events)
            assert all(event.resource_id == "user:recovery-test" for event in events)
        finally:
            db.close()
    finally:
        auth.PBKDF2_ITERATIONS = original_iterations


def test_registration_waits_for_admin_approval_before_login():
    original_iterations = auth.PBKDF2_ITERATIONS
    auth.PBKDF2_ITERATIONS = 1_000
    user_id = "pending-approval-test"
    administrator_id = "approval-admin-test"
    password = "StrongPassword1!"
    questions = [
        {"question": question, "answer": f"Answer {index}"}
        for index, question in enumerate(settings.security_question_options[:3], start=1)
    ]
    try:
        db = TestingSession()
        try:
            db.add(
                User(
                    user_id=administrator_id,
                    password_hash=auth.hash_password("AdminPassword1!"),
                    role="admin",
                    is_approved=True,
                )
            )
            db.commit()
        finally:
            db.close()

        registration = client.post(
            "/api/auth/register",
            json={
                "user_id": user_id,
                "password": password,
                "confirm_password": password,
                "role": "relationship_manager",
                "security_questions": questions,
            },
        )
        assert registration.status_code == 201, registration.text

        status_lookup = client.post(
            "/api/auth/account-status", json={"user_id": user_id}
        )
        assert status_lookup.status_code == 200
        assert status_lookup.json() == {
            "status": "pending",
            "message": "Your account is in the admin queue for approval.",
        }

        pending_login = client.post(
            "/api/auth/login", json={"user_id": user_id, "password": "wrong"}
        )
        assert pending_login.status_code == 403
        assert pending_login.json()["detail"] == "Your account is in the admin queue for approval."

        admin_login = client.post(
            "/api/auth/login",
            json={"user_id": administrator_id, "password": "AdminPassword1!"},
        )
        assert admin_login.status_code == 200, admin_login.text
        queue = client.get("/api/admin/user-approvals")
        assert queue.status_code == 200, queue.text
        assert any(item["user_id"] == user_id for item in queue.json())

        approval = client.post(f"/api/admin/user-approvals/{user_id}/approve")
        assert approval.status_code == 200, approval.text
        assert approval.json()["user_id"] == user_id
        assert client.post("/api/auth/logout").status_code == 204

        approved_login = client.post(
            "/api/auth/login", json={"user_id": user_id, "password": password}
        )
        assert approved_login.status_code == 200, approved_login.text
    finally:
        auth.PBKDF2_ITERATIONS = original_iterations


def test_configured_password_character_counts_are_enforced():
    original_uppercase = settings.PASSWORD_MIN_UPPERCASE
    settings.PASSWORD_MIN_UPPERCASE = 2
    try:
        checks = auth.password_policy_checks("Onlyoneuppercase1!", "another-user")
        assert next(check for check in checks if check["key"] == "uppercase")["met"] is False
        checks = auth.password_policy_checks("TwoUppercaseLetters1!", "another-user")
        assert next(check for check in checks if check["key"] == "uppercase")["met"] is True
    finally:
        settings.PASSWORD_MIN_UPPERCASE = original_uppercase


def test_admin_can_persist_policy_and_business_user_cannot():
    original_iterations = auth.PBKDF2_ITERATIONS
    auth.PBKDF2_ITERATIONS = 1_000
    db = TestingSession()
    try:
        analyst = User(
            user_id="policy-analyst",
            password_hash=auth.hash_password("AnalystPassword1!"),
            role="credit_analyst",
        )
        administrator = User(
            user_id="policy-admin",
            password_hash=auth.hash_password("AdminPassword1!"),
            role="admin",
        )
        db.add_all([analyst, administrator])
        db.commit()
    finally:
        db.close()

    try:
        analyst_login = client.post(
            "/api/auth/login",
            json={"user_id": "policy-analyst", "password": "AnalystPassword1!"},
        )
        assert "Max-Age=1800" in analyst_login.headers["set-cookie"]
        assert client.get("/api/admin/password-policy").status_code == 403

        admin_login = client.post(
            "/api/auth/login",
            json={"user_id": "policy-admin", "password": "AdminPassword1!"},
        )
        assert "Max-Age=900" in admin_login.headers["set-cookie"]
        audit_response = client.get("/api/admin/audit-logs")
        assert audit_response.status_code == 200
        assert audit_response.json()
        assert {
            "event_id",
            "occurred_at",
            "category",
            "event_type",
            "status",
            "source_ip",
            "user_id",
            "resource_id",
            "http_status",
            "error_code",
            "message",
        }.issubset(audit_response.json()[0])
        policy = {
            "min_length": 14,
            "max_length": 100,
            "min_uppercase": 2,
            "min_lowercase": 3,
            "min_digits": 2,
            "min_special": 1,
        }
        saved = client.put("/api/admin/password-policy", json=policy)
        assert saved.status_code == 200, saved.text
        assert client.get("/api/admin/password-policy").json() == policy
        assert client.get("/api/auth/configuration").json()["password_policy"] == policy

        administrative_audit = client.get("/api/admin/administrative-audit-logs")
        assert administrative_audit.status_code == 200
        administrative_events = administrative_audit.json()
        policy_change = next(
            event
            for event in administrative_events
            if event["event_type"] == "update_password_policy"
        )
        assert policy_change["category"] == "administrative_action"
        assert policy_change["user_id"] == "policy-admin"
        assert policy_change["resource_id"] == "security_configuration:password_policy"
        assert policy_change["status"] == "success"
        assert policy_change["source_ip"]

        db = TestingSession()
        try:
            persisted_admin = db.query(User).filter(User.user_id == "policy-admin").one()
            with unittest.TestCase().assertRaises(ValueError):
                auth.validate_password_strength("Abcdefghijkl12!", "new-user", db)
            auth.validate_password_strength("ABcdefghijkl12!", "new-user", db)
            with unittest.TestCase().assertRaises(HTTPException) as denied:
                auth.require_deal_owner("missing-deal", persisted_admin, db)
            assert denied.exception.status_code == 403
            with unittest.TestCase().assertRaises(HTTPException) as create_denied:
                auth.require_relationship_manager(persisted_admin)
            assert create_denied.exception.status_code == 403
        finally:
            db.close()
    finally:
        db = TestingSession()
        try:
            db.query(PasswordPolicyConfiguration).delete()
            db.commit()
        finally:
            db.close()
        auth.PBKDF2_ITERATIONS = original_iterations


def test_admin_bootstrap_repairs_legacy_role_collision():
    original_iterations = auth.PBKDF2_ITERATIONS
    original_user_id = settings.INITIAL_ADMIN_USER_ID
    original_password = settings.INITIAL_ADMIN_PASSWORD
    auth.PBKDF2_ITERATIONS = 1_000
    settings.INITIAL_ADMIN_USER_ID = "bootstrap-user"
    settings.INITIAL_ADMIN_PASSWORD = "SecureBootstrapPassword1!"
    db = TestingSession()
    try:
        user = User(
            user_id="bootstrap-user",
            password_hash=auth.hash_password("OldRelationshipPassword1!"),
            role="relationship_manager",
        )
        db.add(user)
        db.commit()

        auth.seed_initial_users(db)
        db.refresh(user)
        assert user.role == "admin"
        assert auth.verify_password("SecureBootstrapPassword1!", user.password_hash)

        changed_password_hash = auth.hash_password("ChangedAfterBootstrap1!")
        user.password_hash = changed_password_hash
        db.commit()
        auth.seed_initial_users(db)
        db.refresh(user)
        assert user.password_hash == changed_password_hash
    finally:
        db.close()
        settings.INITIAL_ADMIN_USER_ID = original_user_id
        settings.INITIAL_ADMIN_PASSWORD = original_password
        auth.PBKDF2_ITERATIONS = original_iterations


def test_role_based_session_timeouts_and_legacy_cap():
    db = TestingSession()
    try:
        expected_minutes = {
            "relationship_manager": 30,
            "credit_analyst": 30,
            "admin": 15,
        }
        sessions = []
        for role, minutes in expected_minutes.items():
            user = User(
                user_id=f"session-{role}",
                password_hash=auth.hash_password("SessionPassword1!"),
                role=role,
            )
            db.add(user)
            db.commit()
            _, session = auth.create_session(db, user)
            actual_seconds = (session.expires_at - session.created_at).total_seconds()
            assert abs(actual_seconds - minutes * 60) < 1
            sessions.append((session, minutes))

        legacy_session, expected_minutes = sessions[0]
        legacy_session.expires_at = legacy_session.created_at + timedelta(hours=12)
        db.commit()
        assert auth.cap_existing_session_expirations(db) == 1
        db.refresh(legacy_session)
        assert (
            legacy_session.expires_at - legacy_session.created_at
        ).total_seconds() == expected_minutes * 60
    finally:
        db.close()


def test_system_errors_have_separate_audit_category():
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.get("/api/test/system-error")
    assert response.status_code == 500
    assert response.json()["error_code"] == "SYS-001"
    db = TestingSession()
    try:
        event = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == "system_error_for_audit_test")
            .order_by(AuditLog.occurred_at.desc())
            .first()
        )
        assert event is not None
        assert event.category == "system_error"
        assert event.status == "error"
        assert event.http_status == 500
        assert event.source_ip
        assert event.event_id
        assert event.event_id == response.json()["event_id"]
        assert event.error_code == "SYS-001"
        assert event.message == "An unexpected server error occurred."
    finally:
        db.close()


def test_background_error_logs_are_audited():
    handler = DatabaseAuditLogHandler(TestingSession)
    record = logging.LogRecord(
        name="background.worker",
        level=logging.ERROR,
        pathname=__file__,
        lineno=321,
        msg="background task failed",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    db = TestingSession()
    try:
        event = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == "python_error:background.worker")
            .first()
        )
        assert event is not None
        assert event.category == "system_error"
        assert event.status == "error"
        assert event.user_id == "system"
        assert event.source_ip == "system"
        assert event.message == (
            "A background system error occurred. Review restricted server logs for details."
        )
    finally:
        db.close()


class AuthRecoveryTests(unittest.TestCase):
    def test_user_approval_workflow(self):
        test_registration_waits_for_admin_approval_before_login()

    def test_admin_bootstrap_repair(self):
        test_admin_bootstrap_repairs_legacy_role_collision()

    def test_admin_policy_management(self):
        test_admin_can_persist_policy_and_business_user_cannot()

    def test_role_session_timeouts(self):
        test_role_based_session_timeouts_and_legacy_cap()

    def test_system_error_audit_category(self):
        test_system_errors_have_separate_audit_category()

    def test_recovery_flow(self):
        test_three_security_questions_protect_password_reset()

    def test_password_policy_counts(self):
        test_configured_password_character_counts_are_enforced()

    def test_background_error_logging(self):
        test_background_error_logs_are_audited()
