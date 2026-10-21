"""Bounded public-image fetching for local inference servers requiring base64.

Resolve and pin each connection to a public IP; validate every redirect. No cookies,
proxies, private addresses, arbitrary ports or non-image payloads are accepted.
"""
import base64
import ipaddress
import io
import warnings
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from models import public_url

MAX_BYTES = 4 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000


def normalize_image(content):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP", "AVIF"):
                    raise ValueError("Formato immagine non supportato")
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1600, 1600))
                image = image.convert("RGB")
                target = io.BytesIO()
                image.save(target, format="JPEG", quality=85)
                return "data:image/jpeg;base64," + base64.b64encode(target.getvalue()).decode("ascii")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError("Immagine non valida o troppo grande") from exc



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
        return normalize_image(content)
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
