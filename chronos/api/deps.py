"""Auth seam. Person C owns real JWT login; until that lands, B's routers depend on this one function.

Replace `current_user` with C's JWT decoder (same signature: returns {"sub": str, "role": str}); no router changes needed.
"""
import os


def current_user() -> dict:
    # ponytail: stub identity for local runs; C's JWT dependency replaces this.
    return {"sub": os.environ.get("CHRONOS_STUB_USER", "secops"), "role": "security_engineer"}
