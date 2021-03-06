import grpc
import pytest

from couchers import errors
from couchers.crypto import hash_password, random_hex
from couchers.db import session_scope
from couchers.models import Base, LoginToken, PasswordResetToken, SignupToken, User
from pb import api_pb2, auth_pb2, auth_pb2_grpc
from tests.test_fixtures import auth_api_session, db, fast_passwords, generate_user, real_api_session, testconfig


@pytest.fixture(autouse=True)
def _(testconfig):
    pass


def test_UsernameValid(db):
    with auth_api_session(db) as auth_api:
        assert auth_api.UsernameValid(auth_pb2.UsernameValidReq(username="test")).valid

    with auth_api_session(db) as auth_api:
        assert not auth_api.UsernameValid(auth_pb2.UsernameValidReq(username="")).valid


def test_basic_signup(db):
    with auth_api_session(db) as auth_api:
        reply = auth_api.Signup(auth_pb2.SignupReq(email="a@b.com"))
    assert reply.next_step == auth_pb2.SignupRes.SignupStep.SENT_SIGNUP_EMAIL

    # read out the signup token directly from the database for now
    with session_scope(db) as session:
        entry = session.query(SignupToken).filter(SignupToken.email == "a@b.com").one_or_none()
        signup_token = entry.token

    with auth_api_session(db) as auth_api:
        reply = auth_api.SignupTokenInfo(auth_pb2.SignupTokenInfoReq(signup_token=signup_token))

    assert reply.email == "a@b.com"

    with auth_api_session(db) as auth_api:
        reply = auth_api.CompleteSignup(
            auth_pb2.CompleteSignupReq(
                signup_token=signup_token,
                username="frodo",
                name="Räksmörgås",
                city="Minas Tirith",
                birthdate="1980-12-31",
                gender="Robot",
                hosting_status=api_pb2.HOSTING_STATUS_CAN_HOST,
            )
        )
    assert isinstance(reply.token, str)


def test_basic_login(db):
    # Create our test user using signup
    test_basic_signup(db)

    with auth_api_session(db) as auth_api:
        reply = auth_api.Login(auth_pb2.LoginReq(user="frodo"))
    assert reply.next_step == auth_pb2.LoginRes.LoginStep.SENT_LOGIN_EMAIL

    # backdoor to find login token
    with session_scope(db) as session:
        entry = session.query(LoginToken).one_or_none()
        login_token = entry.token

    with auth_api_session(db) as auth_api:
        reply = auth_api.CompleteTokenLogin(auth_pb2.CompleteTokenLoginReq(login_token=login_token))
    assert isinstance(reply.token, str)
    session_token = reply.token

    # log out
    with auth_api_session(db) as auth_api:
        reply = auth_api.Deauthenticate(auth_pb2.DeAuthReq(token=session_token))


def test_login_tokens_invalidate_after_use(db):
    test_basic_signup(db)
    with auth_api_session(db) as auth_api:
        reply = auth_api.Login(auth_pb2.LoginReq(user="frodo"))
    assert reply.next_step == auth_pb2.LoginRes.LoginStep.SENT_LOGIN_EMAIL

    with session_scope(db) as session:
        login_token = session.query(LoginToken).one_or_none().token

    with auth_api_session(db) as auth_api:
        session_token = auth_api.CompleteTokenLogin(auth_pb2.CompleteTokenLoginReq(login_token=login_token)).token

    with auth_api_session(db) as auth_api, pytest.raises(grpc.RpcError):
        # check we can't login again
        auth_api.CompleteTokenLogin(auth_pb2.CompleteTokenLoginReq(login_token=login_token))


def test_banned_user(db):
    test_basic_signup(db)
    with auth_api_session(db) as auth_api:
        reply = auth_api.Login(auth_pb2.LoginReq(user="frodo"))
    assert reply.next_step == auth_pb2.LoginRes.LoginStep.SENT_LOGIN_EMAIL

    with session_scope(db) as session:
        login_token = session.query(LoginToken).one_or_none().token

    with session_scope(db) as session:
        session.query(User).one().is_banned = True

    with auth_api_session(db) as auth_api:
        with pytest.raises(grpc.RpcError):
            auth_api.CompleteTokenLogin(auth_pb2.CompleteTokenLoginReq(login_token=login_token))


def test_invalid_token(db):
    user1, token1 = generate_user(db)
    user2, token2 = generate_user(db)

    wrong_token = random_hex(32)

    with real_api_session(db, wrong_token) as api, pytest.raises(grpc.RpcError) as e:
        res = api.GetUser(api_pb2.GetUserReq(user=user2.username))

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert e.value.details() == "Unauthorized"


def test_password_reset(db, fast_passwords):
    user, token = generate_user(db, hashed_password=hash_password("mypassword"))

    with auth_api_session(db) as auth_api:
        res = auth_api.ResetPassword(
            auth_pb2.ResetPasswordReq(
                user=user.username,
            )
        )

    with session_scope(db) as session:
        token = session.query(PasswordResetToken).one_or_none().token

    with auth_api_session(db) as auth_api:
        res = auth_api.CompletePasswordReset(auth_pb2.CompletePasswordResetReq(password_reset_token=token))

    with session_scope(db) as session:
        user = session.query(User).one()
        assert user.hashed_password is None


def test_password_reset_no_such_user(db):
    user, token = generate_user(db)

    with auth_api_session(db) as auth_api:
        res = auth_api.ResetPassword(
            auth_pb2.ResetPasswordReq(
                user="nonexistentuser",
            )
        )

    with session_scope(db) as session:
        res = session.query(PasswordResetToken).one_or_none()

    assert res is None


def test_password_reset_invalid_token(db, fast_passwords):
    password = random_hex()
    user, token = generate_user(db, hashed_password=hash_password(password))

    with auth_api_session(db) as auth_api:
        res = auth_api.ResetPassword(
            auth_pb2.ResetPasswordReq(
                user=user.username,
            )
        )

    with session_scope(db) as session:
        token = session.query(PasswordResetToken).one_or_none().token

    with auth_api_session(db) as auth_api, pytest.raises(grpc.RpcError) as e:
        res = auth_api.CompletePasswordReset(auth_pb2.CompletePasswordResetReq(password_reset_token="wrongtoken"))
    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert e.value.details() == errors.INVALID_TOKEN

    with session_scope(db) as session:
        user = session.query(User).one()
        assert user.hashed_password == hash_password(password)


# CompleteChangeEmail tested in test_account.py
