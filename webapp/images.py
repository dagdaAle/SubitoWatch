"""Bounded public-image fetching for local inference servers requiring base64.

Resolve and pin each connection to a public IP; validate every redirect. No cookies,
proxies, private addresses, arbitrary ports or non-image payloads are accepted.
"""
import base64
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from models import public_url

MAX_BYTES = 4 * 1024 * 1024


def public_target(url):
    public_url(url)
    parts = urlsplit(url)
    host = parts.hostname
    addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Indirizzo immagine non pubblico')
    # Prefer IPv4 for servers without outbound IPv6; DNS cannot change after this check.
    address = next((a[4][0] for a in addresses if a[0] == socket.AF_INET), addresses[0][4][0])
    target = '[' + address + ']' if ':' in address else address
    if parts.port:
        target += ':' + str(parts.port)
    return urlunsplit((parts.scheme, target, parts.path, parts.query, '')), parts.netloc, host


def fetch_image(url):
    for _ in range(4):
        pinned, host, sni = public_target(url)
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', pinned, headers={'Host':host,'Accept':'image/jpeg,image/png,image/webp'},
                               extensions={'sni_hostname':sni}) as response:
                if response.status_code in (301,302,303,307,308):
                    url = urljoin(url,response.headers['location'])
                    continue
                response.raise_for_status()
                if int(response.headers.get('content-length','0')) > MAX_BYTES:
                    raise ValueError('Immagine troppo grande')
                chunks=[]
                size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError('Immagine troppo grande')
                    chunks.append(chunk)
                content=b''.join(chunks)
        if content.startswith(b'\xff\xd8\xff'):
            mime='image/jpeg'
        elif content.startswith(b'\x89PNG\r\n\x1a\n'):
            mime='image/png'
        elif content.startswith(b'RIFF') and content[8:12]==b'WEBP':
            mime='image/webp'
        else:
            raise ValueError('Formato immagine non supportato')
        return 'data:'+mime+';base64,'+base64.b64encode(content).decode('ascii')
    raise ValueError('Troppi reindirizzamenti immagine')


def prepare(urls):
    encoded, indexes = [], []
    for index,url in enumerate(urls[:6]):
        try:
            encoded.append(fetch_image(url))
            indexes.append(index)
        except (httpx.HTTPError, ValueError, OSError, KeyError):
            continue
    return encoded,indexes
