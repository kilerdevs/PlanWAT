"""Fetch faculty pages through a Cloudflare Worker when the runner's own address is walled.

Imperva (Incapsula) in front of most WAT faculties drops datacenter addresses and, after a
crawl, often the runner's home line too. The public proxy pool in tools/egress can replace
the address for some hosts, but a verified pool this size has no exit for WTC, WIG and WCY
(probed 2026-10-27). A small Cloudflare Worker gets WLO, WEL, WML and WIG through from the
runners' egress; WTC and WCY still answer it with 403 there, so WTC stays on plebania's
direct line and WCY on the pool.

This module is the crawler side of that relay. It wraps a curl_cffi session and sends a GET
for a listed host to ``<PLANWAT_RELAY_URL>?url=<target>`` instead of the target. The caller
keeps the original URL: drivers build the next group URL from their configured base, and
``RelayResponse.url`` is the target, so relative-link handling is unchanged. The Worker
returns the upstream status, validators and body, so conditional refreshes, block
detection, PDFs and the converters see exactly what they would have seen from a direct
fetch.

Configuration (all optional; without PLANWAT_RELAY_URL this is a no-op):

  PLANWAT_RELAY_URL     Worker root URL, e.g. https://planwat-egress.example.workers.dev
  PLANWAT_RELAY_TOKEN   the Worker's bearer secret (``wrangler secret put PLANWAT_RELAY_TOKEN``)
  PLANWAT_RELAY_HOSTS   comma/space separated hosts; default is the known walled-host list;
                        ``off``/``none`` disables the relay without unsetting the URL

The Worker itself lives in tools/egress/cloudflare/ and requires the same token. Requests
to it must leave the egress directly, not through the pool: list its exact hostname in
``EGRESS_DIRECT_HOSTS`` (docs/EGRESS.md).
"""
import os
from urllib.parse import quote, urlsplit

# Hosts that the 2026-10-27 deployment needed the relay for. WIG is listed with both spellings
# because the crawler uses www.wig for listings while some site links use the bare name.
DEFAULT_HOSTS = (
    'wlo.wat.edu.pl',
    'wel.wat.edu.pl',
    'wml.wat.edu.pl',
    'wtc.wat.edu.pl',
    'www.wig.wat.edu.pl',
    'wig.wat.edu.pl',
)

# Only these request headers are forwarded to the Worker (which forwards a subset upstream).
# In particular, never send the session's cookies or an API token for the runner/egress.
FORWARD_HEADERS = frozenset({
    'accept', 'accept-language', 'if-modified-since', 'if-none-match',
    'range', 'referer', 'user-agent',
})


def _split_hosts(raw):
    """Hostnames from a comma/space separated env value, normalized for exact comparison."""
    return tuple(h.strip().lower().rstrip('.') for h in (raw or '').replace(',', ' ').split()
                 if h.strip())


def _env_hosts():
    raw = os.environ.get('PLANWAT_RELAY_HOSTS', '').strip().lower()
    if raw in ('off', 'none', '0', 'false', 'no'):
        return ()
    if not raw or raw in ('auto', 'default', '1', 'true', 'yes'):
        return DEFAULT_HOSTS
    return _split_hosts(raw)


def relay_url():
    """The configured Worker root, or '' when the relay is off/unconfigured."""
    url = os.environ.get('PLANWAT_RELAY_URL', '').strip()
    if not url:
        return ''
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return ''
    # The token is a bearer header, never a URL credential, and a fragment never reaches the
    # server. Reject those spellings instead of silently sending a request somewhere unexpected.
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.fragment or port not in (None, 443)):
        return ''
    return url


def host_relayed(host):
    """True when requests to this host should go through the Worker relay."""
    if not relay_url():
        return False
    host = (host or '').strip().lower().rstrip('.')
    return bool(host) and host in _env_hosts()


def wrap(session):
    """Wrap a curl_cffi session, or return it unchanged when the relay is not configured."""
    url = relay_url()
    if not url:
        return session
    return RelaySession(session, url, os.environ.get('PLANWAT_RELAY_TOKEN', '').strip())


class RelayResponse:
    """A response from the Worker that still looks like the upstream response to the caller.

    ``url`` is the target URL the caller asked for, not the Worker URL. Every other attribute
    (status, headers, content, text, ...) belongs to the Worker response, which the Worker
    built from the upstream one.
    """

    def __init__(self, response, url):
        self._response = response
        self.url = url

    def __getattr__(self, name):
        return getattr(self._response, name)


class RelaySession:
    """A minimal session proxy: only GETs to listed hosts are rerouted."""

    def __init__(self, session, url, token=''):
        self._session = session
        self._url = url.rstrip('/')
        self._token = token

    def get(self, url, **kwargs):
        if not self._should_relay(url):
            return self._session.get(url, **kwargs)
        headers = {
            k: v for k, v in (kwargs.pop('headers', None) or {}).items()
            if k.lower() in FORWARD_HEADERS
        }
        if self._token:
            headers['Authorization'] = f'Bearer {self._token}'
        sep = '&' if '?' in self._url else '?'
        worker_url = f'{self._url}{sep}url={quote(url, safe="")}'
        return RelayResponse(self._session.get(worker_url, headers=headers, **kwargs), url)

    def _should_relay(self, url):
        try:
            parts = urlsplit(url)
        except (TypeError, ValueError):
            return False
        return parts.scheme == 'https' and bool(parts.hostname) and host_relayed(parts.hostname)

    def __getattr__(self, name):
        return getattr(self._session, name)
