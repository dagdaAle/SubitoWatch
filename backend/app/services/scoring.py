"""Card-based recommendation: the model's deal verdict, plus a deterministic check on comparable asking prices."""
from statistics import median
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app import sources


def stale(item):
    stamp=item.get('last_seen')
    return bool(stamp and (datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()>72*3600)


def duplicate_key(item):
    images=item.get('images',[])
    if images:
        part=urlsplit(images[0])
        return part.netloc.lower()+part.path
    return None


def total_cost(item):
    values = [item.get(k) for k in ('price','shipping_cost','fees')]
    return round(sum(values),2) if all(v is not None for v in values) else None


def product_key(card):
    """brand + model, the identity used to compare offers; None when the model is unknown."""
    if not card.get('model'):
        return None
    return ' '.join(str(card.get(k) or '').strip().lower() for k in ('brand','model')).strip()


def excluded(item):
    card=item.get('analysis') or {}
    return card.get('matches_need')=='no' or (item.get('size_check') or {}).get('status')=='exclude'


def recommendation(topic, item, peers):
    card = item.get('analysis') or {}
    total = total_cost(item)
    new = card.get('new_price')
    result = dict(score=None, label='Non determinabile', total_cost=total, reference=None, savings_percent=None,
                  new_price=new, new_savings_percent=round((new-total)/new*100,1) if new and total is not None else None,
                  deal=card.get('deal','unknown'), deal_reason=card.get('deal_reason',''),
                  comparables=[], reasons=[], cost_complete=total is not None)
    if item['state']!='evaluated':
        result['reasons']=['Annuncio non ancora analizzato.']
        return result
    if excluded(item):
        reason=(item.get('size_check') or {}).get('reason') if (item.get('size_check') or {}).get('status')=='exclude' else card.get('matches_reason')
        result.update(label='Non pertinente',reasons=[reason or 'Non è l’oggetto cercato.'])
        return result
    if item['availability']=='unavailable':
        result.update(label='Non disponibile',reasons=['Annuncio non più disponibile.'])
        return result
    if topic['budget'] and total is not None and total>topic['budget']:
        result.update(label='Fuori budget',reasons=['Il costo totale supera il budget.'])
        return result
    result['label']={'yes':'Vera offerta','no':'Non conveniente'}.get(result['deal'],'Convenienza da verificare')
    # The comparison with other offers runs only where the data allows it; it never overrides the label.
    key=product_key(card)
    if (not sources.source_config(item['source'])['pricing'] or stale(item) or item['buying_format']!='fixed'
            or total is None or item['currency']!='EUR' or not key or card.get('condition','unknown')=='unknown'):
        return result
    seen = set()
    seen_images = {duplicate_key(item)} - {None}
    seen_sellers = {item.get('seller','').strip().lower()} - {''}
    candidates=[]
    for other in peers:
        c=other.get('analysis') or {}
        # Separate eBay/Vinted pricing data from other sources and never duplicate a URL.
        if other['id']==item['id'] or other['listing_url'] in seen or other['source'] in ('ebay','vinted') or item['source'] in ('ebay','vinted'):
            continue
        if other['state']!='evaluated' or stale(other) or other['availability']=='unavailable' or other['buying_format']!='fixed':
            continue
        if c.get('matches_need')!='yes' or excluded(other) or product_key(c)!=key or c.get('condition')!=card.get('condition'):
            continue
        if other['currency']!='EUR' or other.get('is_shop')!=item.get('is_shop'):
            continue
        photo=duplicate_key(other)
        seller=other.get('seller','').strip().lower()
        if (photo and photo in seen_images) or (seller and seller in seen_sellers):
            continue
        cost=total_cost(other)
        if cost is not None and cost>0:
            candidates.append({'id':other['id'],'url':other['listing_url'],'total_cost':cost,'kind':'active_asking_price'})
            seen.add(other['listing_url'])
            if photo: seen_images.add(photo)
            if seller: seen_sellers.add(seller)
    result['comparables']=candidates
    if len(candidates)<3:
        return result
    reference=median(c['total_cost'] for c in candidates)
    saving=(reference-total)/reference*100
    # 50 = median asking price, 80 = 30% below.
    result.update(score=round(max(0,min(100,50+saving))),reference=round(reference,2),savings_percent=round(saving,1),
                  reasons=['Confronto con prezzi richiesti di offerte attive equivalenti, non con vendite concluse.'])
    return result
