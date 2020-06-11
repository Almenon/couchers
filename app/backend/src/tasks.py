import logging

def send_login_email(user, token, expiry_text):
    logging.info(f"Pretending to send login email to {user=}:")
    logging.info(f"Email for {user.username=} to {user.email_address=}")
    logging.info(f"Token: {token=} ({token.created=}, {token.expiry=}) ({expiry_text=})")

def send_signup_email():
    logging.info("Pretending to send signup email to {user=}")
