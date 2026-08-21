"""
python -m app.hash_password

Prints the line to paste into the environment. The password itself is never
written anywhere: only the scrypt hash leaves this script.
"""

import getpass

from .auth import hash_password

# One password guards everything, and there is no second factor behind it.
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
