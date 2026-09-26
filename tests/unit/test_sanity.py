"""Sanity check that the package is importable and the test tooling runs."""

import email_processor


def test_package_is_importable() -> None:
    """Verify the email_processor package imports and exposes a docstring."""
    assert email_processor.__doc__
