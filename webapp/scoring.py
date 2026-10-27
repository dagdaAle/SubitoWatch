"""Deterministic comparable-based scoring. Never substitute LLM price guesses."""
from statistics import median
from datetime import datetime, timezone
from urllib.parse import urlsplit

import sources


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


def recommendation(topic, item, peers):
    analysis = item.get('analysis') or {}
    total = total_cost(item)
    result = dict(score=None, label='Non determinabile', total_cost=total, reference=None,
                  savings_percent=None, comparables=[], reasons=[], cost_complete=total is not None)
    if item['state']!='evaluated':
        result['reasons']=['Annuncio non ancora valutato.']
        return result
    if analysis.get('requirement_failures') or analysis.get('relevance',0)<topic['relevance_threshold']:
        result.update(label='Non pertinente',reasons=analysis.get('requirement_failures') or ['Pertinenza insufficiente.'])
        return result
    if not sources.source_config(item['source'])['pricing']:
        result['reasons']=['Valutazione economica non abilitata per questa fonte.']
        return result
    if stale(item):
        result['reasons']=['Ultima verifica più vecchia di 72 ore: aggiorna prima di confrontare.']
        return result
    if item['availability']=='unavailable':
        result.update(label='Non disponibile',reasons=['Annuncio non più disponibile.'])
        return result
    if item['buying_format']!='fixed':
        result['reasons']=['Asta o formato non verificato: prezzo finale non noto.']
        return result
    if total is None or item['currency']!='EUR':
        result['reasons']=['Costo totale incompleto o valuta non confrontabile.']
        return result
    if topic['budget'] and total>topic['budget']:
        result.update(label='Fuori budget',reasons=['Il costo totale supera il budget.'])
        return result
    if analysis.get('missing_parts') or analysis.get('requirement_unknowns') or analysis.get('condition_grade')=='unknown':
        result['reasons']=['Completezza, requisiti o condizioni richiedono verifica.']
        return result
    if not analysis.get('product_key') or not analysis.get('configuration'):
        result['reasons']=['Modello o configurazione non identificati con sufficiente precisione.']
        return result
    seen = set()
    seen_images = {duplicate_key(item)} - {None}
    seen_sellers = {item.get('seller','').strip().lower()} - {''}
    candidates=[]
    for other in peers:
        a=other.get('analysis') or {}
        # Separate eBay pricing data from other sources and never duplicate a URL.
        if other['id']==item['id'] or other['listing_url'] in seen or other['source'] in ('ebay','vinted') or item['source'] in ('ebay','vinted'):
            continue
        if other['state']!='evaluated' or stale(other) or other['availability']=='unavailable' or other['buying_format']!='fixed':
            continue
        if a.get('relevance',0)<topic['relevance_threshold'] or a.get('confidence',0)<70 or a.get('requirement_failures') or a.get('requirement_unknowns') or a.get('missing_parts'):
            continue
        keys=('product_key','configuration','condition_grade')
        if any(str(a.get(k,'')).strip().lower()!=str(analysis.get(k,'')).strip().lower() for k in keys):
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
        result['reasons']=['Servono almeno tre offerte comparabili indipendenti; le richieste attive non provano prezzi di vendita.']
        return result
    reference=median(c['total_cost'] for c in candidates)
    saving=(reference-total)/reference*100
    # 50 = median asking price, 80 = 30% below; uncertainty and evidence limit badges.
    score=round(max(0,min(100,50+saving)))
    confidence=analysis.get('confidence',0)
    if confidence<70 or analysis.get('risks'):
        score=min(score,59)
    result.update(score=score,reference=round(reference,2),savings_percent=round(saving,1),
                  label='Potenziale affare' if score>=75 else 'Prezzo interessante' if score>=60 else 'Prezzo nella media' if score>=40 else 'Poco conveniente',
                  reasons=['Confronto con prezzi richiesti di offerte attive equivalenti, non con vendite concluse.'])
    return result
