"""LinkedIn and Instagram OAuth + publish, against each platform's real API shape.

Both platforms need a developer app registered by a human before any of this
runs — that's account setup, not something this module can do. Everything here
is the code side: build the consent URL, exchange the code, discover the id a
publish call needs, and publish. Every endpoint and header below is the
platform's real one as of this writing; Meta in particular versions its Graph
API and WILL move — GRAPH_VERSION is one env var specifically so a bump doesn't
need a code change.

Env required (see .env.example):
    LinkedIn:   LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI
    Instagram:  INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, INSTAGRAM_REDIRECT_URI

Instagram uses "Instagram API with Instagram Login" (Business Login for
Instagram) — confirmed 2026-09-24 against Meta's own docs. Chosen over the
alternative "Instagram API with Facebook Login for Business" because this
project manages one specific, known account (PKNIC's), not a public app where
strangers connect their own Instagram — so there is no reason to require a
linked Facebook Page in the middle. A prior version of this file DID use the
Facebook Login variant; if you see a `page_token` or "Facebook Page" anywhere
in old notes, that was the wrong choice for this project and has been removed.
"""
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
# LinkedIn-Version is YYYYMM of an SDK release, required on every /rest/* call.
# Pin a real month rather than "latest" so a post's shape can't change under us
# without a deliberate bump — matches the GRAPH_VERSION reasoning below.
LINKEDIN_API_VERSION = os.environ.get("LINKEDIN_API_VERSION", "202601")

# Three DIFFERENT hosts, not a typo — this is how Meta actually split it up:
#   www.instagram.com    the consent screen itself
#   api.instagram.com    the short-lived token exchange (still the OLD host)
#   graph.instagram.com  everything after that: long-lived exchange, account
#                        lookup, publishing. No graph.facebook.com anywhere in
#                        this flow — that host belongs to the OTHER (Facebook
#                        Login for Business) variant this project does not use.
# Sources disagree on the current version (secondary blogs cite v21 through
# v26, and at least one claims graph.instagram.com is unversioned for this
# specific flow) — Meta's own docs were not directly fetchable at build time.
# v23.0 is the one third-party source that explicitly confirmed still working;
# treat this default as a starting point to verify, not a settled fact, and
# check developers.facebook.com/docs/graph-api/changelog before relying on it.
INSTAGRAM_GRAPH_VERSION = os.environ.get("INSTAGRAM_GRAPH_VERSION", "v23.0")
INSTAGRAM_AUTH_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH = f"https://graph.instagram.com/{INSTAGRAM_GRAPH_VERSION}"


class OAuthError(Exception):
    """A platform call failed in a way the caller should show, not retry blindly."""


def _post_form(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise OAuthError(f"{url} -> {e.code}: {e.read().decode(errors='replace')[:400]}") from e


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise OAuthError(f"{url} -> {e.code}: {e.read().decode(errors='replace')[:400]}") from e


def _post_json(url, payload, headers=None):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()) if r.length != 0 else {}
    except urllib.error.HTTPError as e:
        raise OAuthError(f"{url} -> {e.code}: {e.read().decode(errors='replace')[:400]}") from e


def new_state() -> str:
    """One CSRF token per authorize attempt. The caller stores this server-side
    (short TTL, in memory — it's a five-minute secret, not account data) and
    rejects any callback whose `state` doesn't match: without this, a page that
    tricks the user into hitting our callback URL with an attacker's `code`
    could link the attacker's LinkedIn/Instagram account to this app."""
    return secrets.token_urlsafe(24)


# --------------------------------------------------------------------------
# LinkedIn
# --------------------------------------------------------------------------

def linkedin_authorize_url(state: str) -> str:
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    redirect_uri = os.environ.get("LINKEDIN_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise OAuthError("LINKEDIN_CLIENT_ID / LINKEDIN_REDIRECT_URI not set")
    # w_member_social: post as the signed-in person. Posting as a Company Page
    # instead needs w_organization_social, which LinkedIn only grants after a
    # separate Community Management API access review — see LINKEDIN_SCOPES.
    scope = os.environ.get("LINKEDIN_SCOPES", "openid profile w_member_social")
    params = {
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
        "state": state, "scope": scope,
    }
    return f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"


def linkedin_exchange_code(code: str) -> dict:
    """Returns {access_token, expires_in, refresh_token?}. LinkedIn's basic
    3-legged flow does NOT issue a refresh token unless the app has separately
    been granted refresh-token access — most apps get a ~60-day access token
    and nothing else, so callers must be ready to ask the user to reconnect
    rather than assume a silent refresh is possible."""
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    redirect_uri = os.environ.get("LINKEDIN_REDIRECT_URI")
    return _post_form(LINKEDIN_TOKEN_URL, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "client_secret": client_secret,
    })


def linkedin_userinfo(access_token: str) -> dict:
    """The `sub` claim IS the person id used to build the author URN for
    publishing — fetched once at connect time and stored, not re-fetched per
    post."""
    return _get_json(LINKEDIN_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})


def linkedin_publish(access_token: str, member_urn: str, text: str) -> str:
    """POSTs to the Posts API (the current product; the older ugcPosts /
    shares endpoints are deprecated for new integrations). Returns the new
    post's URN, read from the `x-restli-id` response header, which is where
    LinkedIn puts it rather than in the (empty, 201) response body."""
    payload = {
        "author": member_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    req = urllib.request.Request(
        LINKEDIN_POSTS_URL, data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.headers.get("x-restli-id", "")
    except urllib.error.HTTPError as e:
        raise OAuthError(
            f"LinkedIn publish -> {e.code}: {e.read().decode(errors='replace')[:400]}") from e


# --------------------------------------------------------------------------
# Instagram — "Instagram API with Instagram Login" (Business Login for
# Instagram). NOT the Facebook Login for Business variant: this one has no
# Facebook Page anywhere in it. The account holder authorizes directly at
# instagram.com, and the token that comes back is already scoped to their
# Instagram Business/Creator account — there is no separate "page token" to
# discover, which is why this section is shorter than a Page-based flow.
# --------------------------------------------------------------------------

def instagram_authorize_url(state: str) -> str:
    app_id = os.environ.get("INSTAGRAM_APP_ID")
    redirect_uri = os.environ.get("INSTAGRAM_REDIRECT_URI")
    if not app_id or not redirect_uri:
        raise OAuthError("INSTAGRAM_APP_ID / INSTAGRAM_REDIRECT_URI not set")
    # instagram_business_basic: read the connected account's own identity.
    # instagram_business_content_publish: the one this project actually needs.
    # Deliberately NOT requesting instagram_business_manage_messages or
    # instagram_business_manage_comments — this app posts, it doesn't manage a
    # DM inbox or moderate comments, and asking for scopes you don't use is
    # both an unnecessary review-surface and an unnecessary risk if the token
    # ever leaked.
    scope = os.environ.get(
        "INSTAGRAM_SCOPES", "instagram_business_basic,instagram_business_content_publish")
    params = {
        "client_id": app_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": scope, "state": state,
    }
    return f"{INSTAGRAM_AUTH_URL}?{urllib.parse.urlencode(params)}"


def instagram_exchange_code(code: str) -> dict:
    """Returns {access_token, user_id, permissions}. `user_id` is the
    Instagram-scoped id for the account that just authorized — this IS the id
    every later publish call uses; there is no extra lookup step. The short-
    lived token this returns is good for about an hour, which is why the
    caller immediately trades it up via instagram_long_lived_token()."""
    app_id = os.environ.get("INSTAGRAM_APP_ID")
    app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
    redirect_uri = os.environ.get("INSTAGRAM_REDIRECT_URI")
    return _post_form(INSTAGRAM_TOKEN_URL, {
        "client_id": app_id, "client_secret": app_secret, "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    })


def instagram_long_lived_token(short_lived_token: str) -> dict:
    """~60 days, refreshable after the first 24h of its life. Trading up
    immediately is what makes 'connect once' meaningful instead of the token
    dying within the hour."""
    app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
    params = {"grant_type": "ig_exchange_token", "client_secret": app_secret,
              "access_token": short_lived_token}
    return _get_json(f"{INSTAGRAM_GRAPH}/access_token?{urllib.parse.urlencode(params)}")


def instagram_username(access_token: str, ig_user_id: str) -> str:
    """Display label only — connect-time convenience so the UI can show
    "@pknic_official" instead of a bare numeric id. Never used for anything a
    publish call depends on."""
    try:
        return _get_json(
            f"{INSTAGRAM_GRAPH}/{ig_user_id}?fields=username&access_token={access_token}"
        ).get("username", "")
    except OAuthError:
        return ""  # cosmetic only — a failed lookup here must not block connecting


def instagram_publish(access_token: str, ig_user_id: str, caption: str, image_url: str) -> str:
    """Two-step, per Meta's actual API: create a media container, then publish
    it. Instagram has no text-only post type at all — image_url is required
    and must be a URL Meta's servers can fetch (a browser data: URL will not
    work), which is why the caller checks for a real hosted image before
    calling this rather than letting the platform reject it.

    Polls the container's status_code before publishing (bounded: ~10s total).
    Meta's own guidance is to check for FINISHED rather than publish
    immediately — publishing against a container still being processed is a
    real failure mode for larger images, not a theoretical one.
    """
    if not image_url:
        raise OAuthError(
            "Instagram requires an image; this post has none attached "
            "(a data: URL from the browser is not fetchable by Meta's servers — "
            "the image needs to be hosted somewhere public first)")
    container = _post_json(f"{INSTAGRAM_GRAPH}/{ig_user_id}/media", {
        "image_url": image_url, "caption": caption, "access_token": access_token,
    })
    creation_id = container.get("id")
    if not creation_id:
        raise OAuthError(f"Instagram media container creation returned no id: {container}")

    for _ in range(5):
        status = _get_json(
            f"{INSTAGRAM_GRAPH}/{creation_id}?fields=status_code&access_token={access_token}"
        ).get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise OAuthError(f"Instagram failed to process the image container ({creation_id})")
        time.sleep(2)
    # Falls through to publish even without an observed FINISHED: a status
    # check that itself failed or timed out should not silently drop the
    # post — Meta's own media_publish call will reject it with a specific
    # error if the container genuinely isn't ready, which surfaces as an
    # OAuthError from _post_json below rather than a mysterious no-op.

    result = _post_json(f"{INSTAGRAM_GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id, "access_token": access_token,
    })
    post_id = result.get("id")
    if not post_id:
        raise OAuthError(f"Instagram media_publish returned no id: {result}")
    return post_id
