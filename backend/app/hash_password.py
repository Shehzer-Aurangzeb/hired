"""Prompt for a password and print HIRED_PASSWORD_HASH=<scrypt hash> for .env.
Usage: python -m app.hash_password"""

import getpass

from .auth import hash_password

MIN_LENGTH = 12


def main() -> None:
    password = getpass.getpass("Password: ")
    if len(password) < MIN_LENGTH:
        raise SystemExit(
            f"Use at least {MIN_LENGTH} characters. This one password is the only lock."
        )
    if password != getpass.getpass("Again: "):
        raise SystemExit("Those do not match.")
    print()
    print(f"HIRED_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
