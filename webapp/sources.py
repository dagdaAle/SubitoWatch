"""Independent connectors. Access and analysis capabilities are explicit."""
from __future__ import annotations

import os
import time
from html.parser import HTMLParser
from urllib.parse import urlencode


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"):
            self.hidden+=1
        if tag in ("br","p","div","li"):
            self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in ("script","style") and self.hidden:
            self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser=_Text()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())

import httpx

from curl_cffi import requests as cffi

import scraper
from models import ListingInput


def flag(name):
    return os.getenv(name,'').lower() in ('1','true','yes')


class SourceError(RuntimeError):
    """A source failed for a reason safe to show the user."""


def _amount(value):
    """Parse a Vinted money field ({"amount": "3.0"} or a bare number) into a float."""
    if isinstance(value, dict):
        value = value.get('amount')
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def catalog():
    ebay = bool(os.getenv('EBAY_CLIENT_ID') and os.getenv('EBAY_CLIENT_SECRET'))
    return [
        dict(id='manual',name='Annunci inseriti da te',enabled=True,automatic=False,analysis=True,pricing=True,
             detail='Testo e URL delle foto forniti da te. Nessun recupero automatico di URL arbitrari.'),
        dict(id='subito',name='Subito',enabled=flag('BUYWATCHER_ENABLE_SUBITO'),automatic=True,analysis=True,pricing=True,
             detail='Connettore esistente, provincia di Verona, una pagina per ricerca. Attivazione esplicita dopo verifica dell’accesso.'),
        dict(id='ebay',name='eBay',enabled=ebay,automatic=True,analysis=flag('EBAY_ANALYSIS_ALLOWED'),pricing=False,
             detail='Browse API ufficiale. Analisi AI e prezzi richiedono verifica separata dei termini; risultati in sezione dedicata.'),
        dict(id='vinted',name='Vinted',enabled=flag('BUYWATCHER_ENABLE_VINTED'),automatic=True,analysis=True,pricing=False,
             detail='Connettore anonimo al catalogo. Una pagina per ricerca, una foto per annuncio, spedizione sconosciuta. Attivazione esplicita dopo verifica dell’accesso.',
             policy_url='https://www.vinted.it/terms-and-conditions'),
        dict(id='facebook',name='Facebook Marketplace',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Ricerche esterne per topic. Nessuna raccolta automatica: accesso e località si gestiscono su Facebook.',
             policy_url='https://www.facebook.com/legal/automated_data_collection_terms'),
        dict(id='wallapop',name='Wallapop',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Connettore da verificare: nessuna integrazione attiva.'),
        dict(id='astrosell',name='Astrosell',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Fonte astronomica: accesso automatizzato subordinato ad autorizzazione scritta.',
             policy_url='https://www.astrosell.it/condizioni_utilizzo.php'),
    ]


def source_config(source):
    return next(s for s in catalog() if s['id']==source)


def marketplace_searches(topic):
    """Generate navigation links only. Never fetch external pages or change AI cache keys."""
    configs={source['id']:source for source in catalog()}
    definitions=[('vinted','https://www.vinted.it/catalog','search_text'),
                 ('ebay','https://www.ebay.it/sch/i.html','_nkw'),
                 ('facebook','https://www.facebook.com/marketplace/search/','query')]
    result=[]
    for identity,base,param in definitions:
        config=configs[identity]
        monitoring=config['enabled'] and config['automatic'] and identity in topic['sources']
        if identity=='ebay':
            status='automatic' if monitoring else 'setup'
        elif identity=='vinted':
            status='automatic' if monitoring else ('setup' if config['enabled'] else 'external')
        else:
            status='automatic' if monitoring else 'external'
        result.append({'id':identity,'name':config['name'],'monitoring':monitoring,
            'status':status,
            'searches':[{'query':keyword,'url':base+'?'+urlencode({param:keyword})}
                        for keyword in topic['keywords']]})
    return result


class Ebay:
    def __init__(self):
        self.token = None
        self.expiry = 0

    def auth(self):
        if self.token and self.expiry > time.time():
            return self.token
        with httpx.Client(timeout=30) as client:
            r = client.post('https://api.ebay.com/identity/v1/oauth2/token',
                auth=(os.environ['EBAY_CLIENT_ID'],os.environ['EBAY_CLIENT_SECRET']),
                data={'grant_type':'client_credentials','scope':'https://api.ebay.com/oauth/api_scope'})
            r.raise_for_status()
            body = r.json()
            self.token = body['access_token']
            self.expiry = time.time()+body['expires_in']-60
        return self.token

    def get(self, path, params=None):
        with httpx.Client(timeout=30) as client:
            r = client.get('https://api.ebay.com/buy/browse/v1/'+path,
                           headers={'Authorization':'Bearer '+self.auth(), 'X-EBAY-C-MARKETPLACE-ID':'EBAY_IT'},params=params)
            r.raise_for_status()
            return r.json()

    def search(self, keyword, topic):
        body = self.get('item_summary/search', {'q':keyword,'limit':30})
        return body.get('itemSummaries',[])

    def detail(self, summary):
        item = self.get('item/'+summary['itemId'])
        images = [item.get('image',{}).get('imageUrl')]+[x.get('imageUrl') for x in item.get('additionalImages',[])]
        price = item.get('price') or item.get('currentBidPrice') or {}
        seller = item.get('seller',{})
        options = item.get('shippingOptions',[])
        costs = [float(o['shippingCost']['value']) for o in options if o.get('shippingCost',{}).get('value') is not None]
        # No destination-specific quote: shipping remains unknown rather than assuming a minimum.
        return ListingInput(listing_url=item['itemWebUrl'],title=item['title'],
            description=plain_text(item.get('shortDescription') or item.get('description') or '')[:20000],
            price=float(price['value']) if price.get('value') is not None else None,
            currency=price.get('currency','EUR'), shipping_cost=costs[0] if len(options)==1 and len(costs)==1 else None,
            fees=None,town=item.get('itemLocation',{}).get('city',''), images=list(dict.fromkeys(x for x in images if x))[:12],
            condition=item.get('conditionDescription') or item.get('condition') or '',
            seller=seller.get('username',''), source='ebay',external_id=item['itemId'],
            buying_format='auction' if 'AUCTION' in item.get('buyingOptions',[]) else 'fixed',
            availability='active' if (item.get('estimatedAvailabilities') or [{}])[0].get('estimatedAvailabilityStatus')=='IN_STOCK' else 'unknown').model_dump()


EBAY = Ebay()


VINTED_SITE = 'https://www.vinted.it'
VINTED_API = 'https://api.vinted.it'
VINTED_CATALOG = '/svc-catalogue/items'
VINTED_COOKIE = 'access_token_web'
VINTED_COOKIE_TTL = 6 * 3600  # Conservative floor; Vinted sets the real expiry.
VINTED_USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


class Vinted:
    """Anonymous Vinted catalogue connector. One page per search, no detail fetch."""

    def __init__(self):
        self._cookie = None
        self._anon_id = None
        self._expiry = 0.0

    def _refresh_session(self):
        resp = cffi.get(VINTED_SITE + '/', headers={
            'User-Agent': VINTED_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en;q=0.5',
        }, impersonate='chrome', timeout=30)
        if resp.status_code != 200:
            raise SourceError('Vinted non ha rilasciato una sessione anonima.')
        self._cookie = resp.cookies.get(VINTED_COOKIE)
        self._anon_id = resp.headers.get('X-Anon-Id', '')
        if not self._cookie:
            raise SourceError('Vinted non ha rilasciato una sessione anonima.')
        self._expiry = time.time() + VINTED_COOKIE_TTL

    def _ensure_session(self):
        if self._cookie is None or time.time() >= self._expiry:
            self._refresh_session()

    def _headers(self):
        headers = {
            'User-Agent': VINTED_USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'it-IT,it;q=0.9,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Origin': VINTED_SITE,
            'Referer': VINTED_SITE + '/',
            'Locale': 'it-IT',
            'Platform': 'web',
            'X-Next-App': 'marketplace-web',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }
        if self._cookie:
            headers['Cookie'] = f'{VINTED_COOKIE}={self._cookie}'
        if self._anon_id:
            headers['X-Anon-Id'] = self._anon_id
        return headers

    def search(self, keyword, topic, _refreshed=False):
        self._ensure_session()
        params = {'search_text': keyword, 'page': 1, 'per_page': 30, 'order': 'newest_first'}
        if topic.get('budget'):
            params['price_to'] = topic['budget']
        resp = cffi.get(VINTED_API + VINTED_CATALOG, params=params, headers=self._headers(),
                        impersonate='chrome', timeout=30)
        if resp.status_code == 401 and not _refreshed:
            # The anonymous cookie expired mid-run: refresh once, never loop.
            self._refresh_session()
            return self.search(keyword, topic, _refreshed=True)
        if resp.status_code in (403, 429):
            raise SourceError('Vinted ha rifiutato la richiesta.')
        if resp.status_code != 200:
            raise SourceError(f'Vinted ha risposto con lo stato {resp.status_code}.')
        items = resp.json().get('items')
        if not isinstance(items, list):
            raise SourceError('Struttura della risposta Vinted non riconosciuta.')
        return items

    def enrich(self, raw):
        # Catalogue payloads vary between API versions: accept nested objects,
        # relative URLs and photo lists instead of failing the whole listing.
        def text(value):
            if isinstance(value, dict):
                value = value.get('title') or value.get('name') or value.get('label') or ''
            return str(value or '').strip()
        def absolute(value):
            value = text(value) if not isinstance(value, str) else value.strip()
            if value.startswith('//'):
                return 'https:' + value
            if value.startswith('/'):
                return VINTED_SITE + value
            return value
        price = raw.get('price') or {}
        user = raw.get('user') or {}
        photos = [raw.get('photo')] + list(raw.get('photos') or [])
        images = [absolute(p.get('url') or p.get('full_size_url') or '') for p in photos if isinstance(p, dict)]
        item_id = str(raw.get('id') or '')
        url = absolute(raw.get('url') or raw.get('path') or '') or (f'{VINTED_SITE}/items/{item_id}' if item_id else '')
        title = text(raw.get('title'))
        brand = text(raw.get('brand_title') or raw.get('brand'))
        size = text(raw.get('size_title') or raw.get('size'))
        return ListingInput(
            listing_url=url,
            title=(title or 'Annuncio Vinted')[:500],
            description=' '.join(part for part in (title, brand, size) if part),
            price=_amount(price),
            fees=_amount(raw.get('service_fee')),
            currency=(price.get('currency_code') or 'EUR') if isinstance(price, dict) else 'EUR',
            shipping_cost=None,
            images=list(dict.fromkeys(i for i in images if i.startswith('http')))[:12],
            condition=text(raw.get('status')),
            seller=text(user.get('login')) if isinstance(user, dict) else '',
            is_shop=bool(user.get('business')) if isinstance(user, dict) else False,
            buying_format='fixed',
            source='vinted',
            external_id=item_id,
            availability='active',
        ).model_dump()


VINTED = Vinted()


def search(source, keyword, topic):
    if source=='ebay':
        return EBAY.search(keyword,topic)
    if source=='subito':
        # Retain the old scope and pacing. Topic budget applies to TOTAL later.
        return scraper.search(keyword, comune=topic['location'], pages=1)
    if source=='vinted':
        return VINTED.search(keyword, topic)
    return []


def enrich(source, raw):
    if source=='ebay':
        return EBAY.detail(raw)
    if source=='vinted':
        return VINTED.enrich(raw)
    return ListingInput(listing_url=raw['listing_url'],title=raw['title'],description=raw.get('description',''),
        price=raw.get('price'),town=raw.get('town',''),images=raw.get('images') or ([raw['thumbnail']] if raw.get('thumbnail') else []),
        seller=raw.get('shop_name',''),is_shop=raw.get('is_shop',False),source='subito',published_at=raw.get('date',''),
        buying_format='unknown',availability='unknown').model_dump()
