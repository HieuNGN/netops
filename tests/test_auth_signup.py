"""Tests for /api/auth/signup and related user management."""

import pytest
import pytest_asyncio
import os
import tempfile

os.environ.setdefault("JWT_SECRET", "test-secret-for-tests-only-32chars")

STRONG_PW = "Sup3r$ecret!"

# Pre-built fixtures in this file use STRONG_PW. Individual validation tests
# use deliberately weak passwords to exercise rejection.


@pytest_asyncio.fixture
async def sqlite_db():
    """Fresh SQLite DB for auth tests."""
    from src.storage.sqlite_client import AsyncSQLiteClient
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()
    await db.init_db()
    yield db, tmp.name
    await db.close()
    try: os.unlink(tmp.name)
    except OSError: pass


@pytest_asyncio.fixture
async def app_with_db(sqlite_db):
    """Build a fresh FastAPI app instance sharing state, wired to sqlite db."""
    db, _ = sqlite_db
    from prometheus_client import REGISTRY
    from fastapi import FastAPI, Depends
    from fastapi.responses import JSONResponse
    from httpx import AsyncClient, ASGITransport
    from src.api.services.auth import (
        hash_password, verify_password, create_access_token, current_user as need_auth,
    )
    from pydantic import BaseModel, EmailStr, Field, field_validator
    import re

    class LoginRequest(BaseModel):
        username: str
        password: str

    class SignupRequest(BaseModel):
        username: str = Field(min_length=3, max_length=32)
        email: EmailStr
        name: str = Field(min_length=1, max_length=64)
        password: str = Field(min_length=8, max_length=128)

        @field_validator("username")
        @classmethod
        def _username_safe(cls, v: str) -> str:
            if not re.match(r"^[A-Za-z0-9_.-]+$", v):
                raise ValueError("username may only contain letters, digits, _.-")
            return v

        @field_validator("password")
        @classmethod
        def _password_strong(cls, v: str) -> str:
            if not re.search(r"[a-z]", v):
                raise ValueError("password must include a lowercase letter")
            if not re.search(r"[A-Z]", v):
                raise ValueError("password must include an uppercase letter")
            if not re.search(r"\d", v):
                raise ValueError("password must include a digit")
            if not re.search(r"[^A-Za-z0-9]", v):
                raise ValueError("password must include a symbol")
            return v

    await db.create_user("admin", hash_password("admin"), email="admin@example.com", name="Admin")

    app = FastAPI()

    @app.post("/api/auth/login")
    async def auth_login(req: LoginRequest):
        user = await db.get_user_by_username(req.username)
        if not user or not verify_password(req.password, user["password_hash"]):
            return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
        token = create_access_token(req.username)
        return {"token": token, "username": req.username, "role": user.get("role", "admin")}

    @app.post("/api/auth/signup", status_code=201)
    async def auth_signup(req: SignupRequest):
        if await db.get_user_by_username(req.username):
            return JSONResponse({"detail": "Username already taken"}, status_code=409)
        if await db.get_user_by_email(req.email):
            return JSONResponse({"detail": "Email already registered"}, status_code=409)
        user = await db.create_user(
            req.username, hash_password(req.password), email=req.email, name=req.name,
        )
        token = create_access_token(req.username)
        return {
            "token": token,
            "username": user["username"],
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role", "admin"),
        }

    @app.get("/api/auth/me")
    async def auth_me(user: str = Depends(need_auth)):
        row = await db.get_user_by_username(user)
        if row:
            return {
                "username": row["username"],
                "email": row.get("email"),
                "name": row.get("name"),
                "role": row.get("role", "admin"),
                "authenticated": True,
            }
        return {"username": user, "authenticated": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_signup_creates_user_and_returns_token(app_with_db):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane",
        "email": "jane@example.com",
        "name": "Jane Operator",
        "password": STRONG_PW,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "jane"
    assert body["email"] == "jane@example.com"
    assert body["name"] == "Jane Operator"
    assert "token" in body and len(body["token"]) > 20


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_username(app_with_db):
    payload = {
        "username": "jane",
        "email": "jane@example.com",
        "name": "Jane",
        "password": STRONG_PW,
    }
    r1 = await app_with_db.post("/api/auth/signup", json=payload)
    assert r1.status_code == 201
    r2 = await app_with_db.post("/api/auth/signup", json=payload)
    assert r2.status_code == 409
    assert "taken" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email(app_with_db):
    r1 = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "jane@example.com",
        "name": "Jane", "password": STRONG_PW,
    })
    assert r1.status_code == 201
    r2 = await app_with_db.post("/api/auth/signup", json={
        "username": "jane2", "email": "jane@example.com",
        "name": "Jane2", "password": STRONG_PW,
    })
    assert r2.status_code == 409
    assert "email" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_signup_rejects_short_password(app_with_db):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "jane@example.com",
        "name": "Jane", "password": "short",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_signup_rejects_bad_email(app_with_db):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "not-an-email",
        "name": "Jane", "password": STRONG_PW,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_signup_rejects_invalid_username(app_with_db):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane doe!", "email": "jane@example.com",
        "name": "Jane", "password": STRONG_PW,
    })
    assert r.status_code == 422


@pytest.mark.parametrize("weak,expected_in_msg", [
    ("alllower1!", "uppercase"),
    ("ALLUPPER1!", "lowercase"),
    ("NoDigits!!", "digit"),
    ("NoSymbol1", "symbol"),
    ("Short1!", None),
])
@pytest.mark.asyncio
async def test_signup_enforces_strong_password(app_with_db, weak, expected_in_msg):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "jane@example.com",
        "name": "Jane", "password": weak,
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and len(detail) > 0
    if expected_in_msg is not None:
        joined = " ".join(str(e.get("msg", "")) for e in detail).lower()
        assert expected_in_msg in joined, f"missing {expected_in_msg!r} in {detail}"


@pytest.mark.asyncio
async def test_422_response_shape_supports_field_error_extraction(app_with_db):
    """Frontend reads detail[0].msg — make sure the contract holds."""
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "not-an-email",
        "name": "Jane", "password": STRONG_PW,
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "msg" in detail[0]
    assert "loc" in detail[0]


@pytest.mark.asyncio
async def test_auth_me_returns_user_fields(app_with_db):
    r = await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "jane@example.com",
        "name": "Jane Operator", "password": STRONG_PW,
    })
    token = r.json()["token"]
    r2 = await app_with_db.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["username"] == "jane"
    assert body["email"] == "jane@example.com"
    assert body["name"] == "Jane Operator"


@pytest.mark.asyncio
async def test_newly_signed_up_user_can_log_in(app_with_db):
    await app_with_db.post("/api/auth/signup", json={
        "username": "jane", "email": "jane@example.com",
        "name": "Jane", "password": STRONG_PW,
    })
    r = await app_with_db.post("/api/auth/login", json={"username": "jane", "password": STRONG_PW})
    assert r.status_code == 200
    assert "token" in r.json()


@pytest.mark.asyncio
async def test_signup_recovers_from_sqlite_lock(monkeypatch):
    """create_user / get_user_by_username / get_user_by_email must retry on
    transient 'database is locked' errors raised by concurrent writers
    (e.g. the SNMP poller holding a write transaction)."""
    from src.storage.sqlite_client import AsyncSQLiteClient
    import tempfile, os, sqlite3, asyncio

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()
    await db.init_db()

    real_exec = db._db.execute
    calls = {"n": 0}

    async def flaky_exec(sql, params=()):
        calls["n"] += 1
        # Fail the first two execute() calls with locked, then pass through
        if calls["n"] <= 2 and "users" in (sql if isinstance(sql, str) else ""):
            raise sqlite3.OperationalError("database is locked")
        return await real_exec(sql, params)

    monkeypatch.setattr(db._db, "execute", flaky_exec)

    user = await db.create_user("retryme", "hashed", email="r@x.com", name="R")
    assert user["username"] == "retryme"
    assert calls["n"] >= 3

    # get_user_by_username and get_user_by_email should also survive flakiness
    calls["n"] = 0
    found = await db.get_user_by_username("retryme")
    assert found is not None
    found2 = await db.get_user_by_email("r@x.com")
    assert found2 is not None

    await db.close()
    os.unlink(tmp.name)
