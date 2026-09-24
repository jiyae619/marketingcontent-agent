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
    Instagram:  META_APP_ID, META_APP_SECRET, META_REDIRECT_URI
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

META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
META_GRAPH = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
META_AUTH_URL = f"https://www.facebook.com/{META_GRAPH_VERSION}/dialog/oauth"


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
# Instagram (via the Meta Graph API — Facebook Login for Business)
# --------------------------------------------------------------------------
# There is no "Instagram API" that stands alone: publishing goes through a
# Facebook Page that has an Instagram Professional account linked to it, using
# a Page-scoped access token, not the user token OAuth itself returns.

def instagram_authorize_url(state: str) -> str:
    app_id = os.environ.get("META_APP_ID")
    redirect_uri = os.environ.get("META_REDIRECT_URI")
    if not app_id or not redirect_uri:
        raise OAuthError("META_APP_ID / META_REDIRECT_URI not set")
    scope = os.environ.get(
        "META_SCOPES",
        "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement")
    params = {
        "client_id": app_id, "redirect_uri": redirect_uri, "state": state, "scope": scope,
        "response_type": "code",
    }
    return f"{META_AUTH_URL}?{urllib.parse.urlencode(params)}"


def instagram_exchange_code(code: str) -> dict:
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")
    redirect_uri = os.environ.get("META_REDIRECT_URI")
    params = {"client_id": app_id, "redirect_uri": redirect_uri,
              "client_secret": app_secret, "code": code}
    return _get_json(f"{META_GRAPH}/oauth/access_token?{urllib.parse.urlencode(params)}")


def instagram_long_lived_token(short_lived_token: str) -> dict:
    """The token from the code exchange is short-lived (~1-2h). Trading it for
    a long-lived one (~60 days) is what makes 'connect once' meaningful instead
    of the user reconnecting every session."""
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")
    params = {"grant_type": "fb_exchange_token", "client_id": app_id,
              "client_secret": app_secret, "fb_exchange_token": short_lived_token}
    return _get_json(f"{META_GRAPH}/oauth/access_token?{urllib.parse.urlencode(params)}")


def instagram_discover_account(user_token: str) -> dict:
    """Walks user token -> Facebook Pages the user manages -> each Page's linked
    Instagram Professional account, and returns the first Page that has one,
    with the PAGE token (publishing needs the Page's own token, which is
    different from the user token used to discover it) and the IG account id
    and username. Raises OAuthError with a specific, actionable message when
    the chain is missing a link — "connected" but "no Page" and "connected but
    the Page has no linked Instagram account" are different problems for the
    person setting this up to fix.
    """
    pages = _get_json(f"{META_GRAPH}/me/accounts?access_token={user_token}").get("data", [])
    if not pages:
        raise OAuthError(
            "no Facebook Pages found for this account — Instagram publishing "
            "requires a Facebook Page with this Instagram account linked as "
            "its Professional account")
    for page in pages:
        page_id, page_token = page["id"], page["access_token"]
        info = _get_json(
            f"{META_GRAPH}/{page_id}?fields=instagram_business_account&access_token={page_token}")
        ig = info.get("instagram_business_account")
        if ig:
            ig_id = ig["id"]
            username = _get_json(
                f"{META_GRAPH}/{ig_id}?fields=username&access_token={page_token}"
            ).get("username", "")
            return {"ig_user_id": ig_id, "username": username,
                    "page_id": page_id, "page_token": page_token}
    raise OAuthError(
        f"found {len(pages)} Facebook Page(s), but none has an Instagram "
        "Professional account linked — link one in Meta Business Suite, then reconnect")


def instagram_publish(page_token: str, ig_user_id: str, caption: str, image_url: str) -> str:
    """Two-step, per Meta's actual API: create a media container, then publish
    it. Instagram has no text-only post type at all — image_url is required
    and must be a URL Meta's servers can fetch (a browser data: URL will not
    work), which is why the caller checks for a real hosted image before
    calling this rather than letting the platform reject it."""
    if not image_url:
        raise OAuthError(
            "Instagram requires an image; this post has none attached "
            "(a data: URL from the browser is not fetchable by Meta's servers — "
            "the image needs to be hosted somewhere public first)")
    container = _post_json(f"{META_GRAPH}/{ig_user_id}/media", {
        "image_url": image_url, "caption": caption, "access_token": page_token,
    })
    creation_id = container.get("id")
    if not creation_id:
        raise OAuthError(f"Instagram media container creation returned no id: {container}")
    result = _post_json(f"{META_GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id, "access_token": page_token,
    })
    post_id = result.get("id")
    if not post_id:
        raise OAuthError(f"Instagram media_publish returned no id: {result}")
    return post_id
