"""Independent connectors. Access and analysis capabilities are explicit."""
from __future__ import annotations

import os
import time
from html.parser import HTMLParser


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

import scraper
from models import ListingInput


def flag(name):
    return os.getenv(name,'').lower() in ('1','true','yes')


def catalog():
    ebay = bool(os.getenv('EBAY_CLIENT_ID') and os.getenv('EBAY_CLIENT_SECRET'))
    return [
        dict(id='manual',name='Annunci inseriti da te',enabled=True,automatic=False,analysis=True,pricing=True,
             detail='Testo e URL delle foto forniti da te. Nessun recupero automatico di URL arbitrari.'),
        dict(id='subito',name='Subito',enabled=flag('BUYWATCHER_ENABLE_SUBITO'),automatic=True,analysis=True,pricing=True,
             detail='Connettore esistente, provincia di Verona, una pagina per ricerca. Attivazione esplicita dopo verifica dell’accesso.'),
        dict(id='ebay',name='eBay',enabled=ebay,automatic=True,analysis=flag('EBAY_ANALYSIS_ALLOWED'),pricing=False,
             detail='Browse API ufficiale. Analisi AI e prezzi richiedono verifica separata dei termini; risultati in sezione dedicata.'),
        dict(id='vinted',name='Vinted',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Accesso automatizzato non attivato: serve un percorso autorizzato.',policy_url='https://www.vinted.it/terms-and-conditions'),
        dict(id='wallapop',name='Wallapop',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Connettore da verificare: nessuna integrazione attiva.'),
        dict(id='astrosell',name='Astrosell',enabled=False,automatic=False,analysis=False,pricing=False,
             detail='Fonte astronomica: accesso automatizzato subordinato ad autorizzazione scritta.',
             policy_url='https://www.astrosell.it/condizioni_utilizzo.php'),
    ]


def source_config(source):
    return next(s for s in catalog() if s['id']==source)


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


def search(source, keyword, topic):
    if source=='ebay':
        return EBAY.search(keyword,topic)
    if source=='subito':
        # Retain the old scope and pacing. Topic budget applies to TOTAL later.
        return scraper.search(keyword, comune=topic['location'], pages=1)
    return []


def enrich(source, raw):
    if source=='ebay':
        return EBAY.detail(raw)
    return ListingInput(listing_url=raw['listing_url'],title=raw['title'],description=raw.get('description',''),
        price=raw.get('price'),town=raw.get('town',''),images=raw.get('images') or ([raw['thumbnail']] if raw.get('thumbnail') else []),
        seller=raw.get('shop_name',''),is_shop=raw.get('is_shop',False),source='subito',published_at=raw.get('date',''),
        buying_format='unknown',availability='unknown').model_dump()
