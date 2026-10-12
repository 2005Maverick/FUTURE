"""Unit tests for the secret/PII scanner (part of E-10).

Secret-looking fixtures are assembled at runtime so this file itself never
contains a literal that the scanner would block.
"""
import precommit_scan as scan

FAKE_GH = "gh" + "o_" + "A1b2C3d4" * 5
FAKE_KAGGLE = "KG" + "AT_" + "a1b2c3d4" * 4
FAKE_SK = "s" + "k-ant-" + "Zz09" * 8
FAKE_JWT = "ey" + "J" + "a" * 20 + ".ey" + "J" + "b" * 20 + "." + "c" * 15
FAKE_PHONE = "+91 " + "98" + "765" + " " + "43210"


def kinds(text, denylist=None):
    return {f.kind for f in scan.scan_text("x.py", text, denylist)}


def test_clean_code_passes():
    assert kinds("def add(a, b):\n    return a + b\n") == set()


def test_docs_mentioning_token_prefixes_pass():
    assert kinds("Scanner blocks prefixes like sk-, gho_, KGAT_ (see docs).") == set()


def test_github_token_blocked():
    assert "github_token" in kinds(f"TOKEN={FAKE_GH}")


def test_kaggle_token_blocked():
    assert "kaggle_token" in kinds(f"k = '{FAKE_KAGGLE}'")


def test_anthropic_style_key_blocked():
    assert "openai_or_anthropic_key" in kinds(FAKE_SK)


def test_jwt_blocked():
    assert "jwt" in kinds(f"service_role: {FAKE_JWT}")


def test_assigned_secret_blocked():
    assert "assigned_secret" in kinds("EXA_API_" + "KEY = " + "q1w2e3r4" * 3)


def test_assigned_identifier_without_digits_passes():
    assert "assigned_secret" not in kinds("token = get_token_from_environment()")


def test_indian_mobile_blocked_in_several_formats():
    assert "indian_mobile" in kinds(f"call {FAKE_PHONE}")
    assert "indian_mobile" in kinds("phone: " + "98765" + "43210")


def test_numbers_that_are_not_phones_pass():
    assert "indian_mobile" not in kinds("ids = [1234567890123, 42, 2026]")
    assert "indian_mobile" not in kinds("version 1.79M articles, 132 deployments")


def test_denylist_matches_case_insensitively():
    denylist = ["someone@example.org"]
    assert "denylisted_pii" in kinds("mail Someone@Example.org now", denylist)


def test_allow_marker_suppresses_reviewed_line():
    assert kinds(f"{FAKE_GH}  # scan:allow") == set()


def test_blocked_paths():
    for path in ["private/cv.docx", ".env", ".env.local", "a/b/Connections.csv", "id.pem"]:
        assert scan.check_path(path), path
    assert not scan.check_path("core/future/config.py")
    assert not scan.check_path("docs/env-setup.md")
