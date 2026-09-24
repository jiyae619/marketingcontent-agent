#!/usr/bin/env python3
"""Write-path validation for OAuth account storage and the publish queue.

Covers what would be expensive to get wrong: a token stored in plaintext, a
publish job that sends text nobody approved, a double-claim that could double-
post, and a disconnect that leaves a usable token behind. No network call is
made — oauth_providers' URL builders are checked as pure functions, and
linkedin_publish/instagram_publish are exercised only through server.py's job
runner logic replicated here at the data-layer boundary (the real HTTP calls
live in oauth_providers.py and are exactly what a human clicking "Connect"
exercises for real, which no test double stands in for honestly).

SAFETY: binds throwaway FEEDBACK_DB_PATH and OAUTH_KEY_PATH BEFORE importing
feedback_db / oauth_crypto, and refuses to run against the real files —
same guard as scripts/test_feedback_db.py.

    Run:  python3 scripts/test_oauth.py
"""
import hashlib
import os
import sys
import tempfile
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

DEFAULT_DB = os.path.join(_REPO_ROOT, "testing/results/feedback.db")
DEFAULT_KEY = os.path.join(_REPO_ROOT, ".oauth_key")

_tmp = tempfile.mkdtemp(prefix="oauthtest_")
_env_db = os.environ.get("FEEDBACK_DB_PATH")
if not _env_db or os.path.abspath(_env_db) == os.path.abspath(DEFAULT_DB):
    os.environ["FEEDBACK_DB_PATH"] = os.path.join(_tmp, "test.db")
_env_key = os.environ.get("OAUTH_KEY_PATH")
if not _env_key or os.path.abspath(_env_key) == os.path.abspath(DEFAULT_KEY):
    os.environ["OAUTH_KEY_PATH"] = os.path.join(_tmp, "test.oauth_key")

assert os.path.abspath(os.environ["FEEDBACK_DB_PATH"]) != os.path.abspath(DEFAULT_DB), \
    "refusing to run against the real feedback.db"
assert os.path.abspath(os.environ["OAUTH_KEY_PATH"]) != os.path.abspath(DEFAULT_KEY), \
    "refusing to run against the real .oauth_key"

import feedback_db as db  # noqa: E402
import oauth_crypto  # noqa: E402
import oauth_providers as op  # noqa: E402

db.init_db()

CHECKS = 0


def check(label, cond):
    global CHECKS
    CHECKS += 1
    assert cond, f"FAILED: {label}"
    print(f"  ok  {label}")


def main():
    # --- oauth_crypto: round trip and key-file hygiene ----------------------
    pt = "AQV-secret-access-token-value"
    ct = oauth_crypto.encrypt(pt)
    check("encrypted token is not the plaintext", ct != pt.encode())
    check("decrypt reverses encrypt", oauth_crypto.decrypt(ct) == pt)
    check("key file was created with owner-only permissions",
          oct(os.stat(os.environ["OAUTH_KEY_PATH"]).st_mode)[-3:] == "600")

    try:
        oauth_crypto.decrypt(b"not-a-real-fernet-token")
        raise AssertionError("decrypt of garbage should have raised")
    except ValueError:
        check("a non-decryptable token raises ValueError, not a crypto-library exception", True)

    # --- save / list / get / disconnect --------------------------------------
    acc_id = db.save_oauth_account(
        platform="linkedin", external_id="urn:li:person:abc123", label="Grace Park",
        access_token="li-access-tok", refresh_token=None,
        scope="openid profile w_member_social", expires_at=time.time() + 3600)
    accounts = db.list_oauth_accounts()
    check("saved account appears in the list", any(a["id"] == acc_id for a in accounts))
    check("listed account has NO token field at all",
          all("access_token" not in a and "access_token_enc" not in a for a in accounts))

    tok = db.get_oauth_tokens(acc_id)
    check("get_oauth_tokens decrypts the access token", tok["access_token"] == "li-access-tok")
    check("get_oauth_tokens returns None refresh token as None, not a decrypt error",
          tok["refresh_token"] is None)

    same_id = db.save_oauth_account(
        platform="linkedin", external_id="urn:li:person:abc123", label="Grace Park (renamed)",
        access_token="li-access-tok-v2")
    check("reconnecting the same (platform, external_id) UPDATES the row, not a duplicate",
          same_id == acc_id and len(db.list_oauth_accounts()) == 1)
    check("the update replaced the token",
          db.get_oauth_tokens(acc_id)["access_token"] == "li-access-tok-v2")

    ok = db.disconnect_oauth_account(acc_id)
    check("disconnect reports success", ok)
    check("disconnected account is gone from the active list",
          not any(a["id"] == acc_id for a in db.list_oauth_accounts()))
    check("disconnecting an already-disconnected account is a no-op, not an error",
          db.disconnect_oauth_account(acc_id) is False)
    check("get_oauth_tokens returns None for a disconnected account",
          db.get_oauth_tokens(acc_id) is None)

    # --- publish queue: the fingerprint invariant ----------------------------
    # No page_token for Instagram anymore — Instagram API with Instagram Login
    # publishes with the same access_token the account connected with.
    ig_acc = db.save_oauth_account(platform="instagram", external_id="ig:999",
                                   label="@pknic", access_token="ig-user-tok")
    gen_id = db.log_generation(platform="linkedin", original_input="brief",
                               generated_content="Original draft text.")

    try:
        db.enqueue_publish(generation_id=gen_id, platform="linkedin", oauth_account_id=acc_id)
        raise AssertionError("enqueue with no approve/edit verdict should have raised")
    except ValueError as e:
        check("cannot enqueue a generation with no recorded approval", "no approve/edit" in str(e))

    approved_text = "Final, human-approved text."
    db.log_feedback(generation_id=gen_id, platform="linkedin", verdict="edit",
                    original_content="Original draft text.", final_content=approved_text,
                    flag_categories=["tone"])
    job = db.enqueue_publish(generation_id=gen_id, platform="linkedin", oauth_account_id=same_id)
    check("enqueue reads the APPROVED text, not generations.generated_content",
          job["content"] == approved_text)
    check("fingerprint is sha256 of the exact approved text",
          job["content_fingerprint"] == hashlib.sha256(approved_text.encode()).hexdigest())

    try:
        db.enqueue_publish(generation_id=gen_id, platform="instagram", oauth_account_id=ig_acc)
        raise AssertionError("platform mismatch should have raised")
    except ValueError as e:
        check("enqueue rejects a platform that doesn't match the generation's own",
              "not 'instagram'" in str(e) or "instagram" in str(e))

    # --- due jobs, claiming, completion ---------------------------------------
    due = db.due_publish_jobs()
    check("an immediate (no scheduled_for) job is due now", any(j["id"] == job["id"] for j in due))

    future_gen = db.log_generation(platform="linkedin", original_input="b2", generated_content="d2")
    db.log_feedback(generation_id=future_gen, platform="linkedin", verdict="approve",
                    original_content="d2", final_content="d2")
    future_job = db.enqueue_publish(generation_id=future_gen, platform="linkedin",
                                    oauth_account_id=same_id, scheduled_for=time.time() + 3600)
    due_now = {j["id"] for j in db.due_publish_jobs()}
    check("a job scheduled an hour out is NOT due yet", future_job["id"] not in due_now)
    check("a job scheduled in the past IS due",
          db.enqueue_publish(generation_id=future_gen, platform="linkedin",
                             oauth_account_id=same_id, scheduled_for=time.time() - 5)["id"]
          in {j["id"] for j in db.due_publish_jobs()})

    check("claiming a pending job succeeds", db.claim_publish_job(job["id"]))
    check("claiming the SAME job again fails — this is the double-post guard",
          db.claim_publish_job(job["id"]) is False)

    db.complete_publish_job(job["id"], remote_post_id="urn:li:share:999")
    log = db.publish_log_for(gen_id)
    check("completed job shows status=success with the remote id",
          log[0]["status"] == "success" and log[0]["remote_post_id"] == "urn:li:share:999")

    failing = db.enqueue_publish(generation_id=gen_id, platform="linkedin", oauth_account_id=same_id)
    db.claim_publish_job(failing["id"])
    db.complete_publish_job(failing["id"], error="LinkedIn 401: token expired")
    log2 = db.publish_log_for(gen_id)
    check("a failed job records the error and status=failed",
          log2[0]["status"] == "failed" and "401" in log2[0]["error"])

    cancelable = db.enqueue_publish(generation_id=gen_id, platform="linkedin", oauth_account_id=same_id)
    check("a pending job can be canceled", db.cancel_publish_job(cancelable["id"]))
    claimed_then_cancel = db.enqueue_publish(generation_id=gen_id, platform="linkedin",
                                             oauth_account_id=same_id)
    db.claim_publish_job(claimed_then_cancel["id"])
    check("a job already claimed (publishing) cannot be canceled out from under it",
          db.cancel_publish_job(claimed_then_cancel["id"]) is False)

    # --- oauth_providers: URL builders, no network ---------------------------
    for k in ("LINKEDIN_CLIENT_ID", "LINKEDIN_REDIRECT_URI",
             "INSTAGRAM_APP_ID", "INSTAGRAM_REDIRECT_URI"):
        os.environ.pop(k, None)
    try:
        op.linkedin_authorize_url("state123")
        raise AssertionError("should have raised with no client id configured")
    except op.OAuthError:
        check("linkedin_authorize_url refuses to build a URL with no client id", True)

    os.environ["LINKEDIN_CLIENT_ID"] = "test-client-id"
    os.environ["LINKEDIN_REDIRECT_URI"] = "http://localhost:8081/api/oauth/linkedin/callback"
    url = op.linkedin_authorize_url("state123")
    check("linkedin authorize URL carries the state and client id",
          "state=state123" in url and "test-client-id" in url
          and url.startswith(op.LINKEDIN_AUTH_URL))

    try:
        op.instagram_authorize_url("state456")
        raise AssertionError("should have raised with no app id configured")
    except op.OAuthError:
        check("instagram_authorize_url refuses to build a URL with no app id", True)

    os.environ["INSTAGRAM_APP_ID"] = "test-app-id"
    os.environ["INSTAGRAM_REDIRECT_URI"] = "http://localhost:8081/api/oauth/instagram/callback"
    ig_url = op.instagram_authorize_url("state456")
    check("instagram authorize URL carries the state and app id, hits instagram.com not facebook.com",
          "state=state456" in ig_url and "test-app-id" in ig_url
          and ig_url.startswith(op.INSTAGRAM_AUTH_URL) and "facebook.com" not in ig_url)
    check("instagram authorize URL requests only the scopes this app actually uses",
          "instagram_business_content_publish" in ig_url
          and "instagram_business_manage_messages" not in ig_url)

    s1, s2 = op.new_state(), op.new_state()
    check("new_state() is unique per call", s1 != s2)

    print(f"\n{'='*60}\nALL {CHECKS} CHECKS PASSED\n{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
