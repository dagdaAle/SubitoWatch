"""Compare the sizes extracted on the card with the buyer profile. No EU/UK/US conversion."""
from app.schemas import CLOTHING_SIZES

VERSION = 'sizes-card-1'
NONE = {'status':'none','reason':''}


def preferences(topic, profile):
    scope=topic.get('profile_scope','none')
    values={}
    if scope in ('fashion','footwear') and profile.get('shoe_size_eu') is not None:
        values['shoe_size_eu']=profile['shoe_size_eu']
    if scope in ('fashion','clothing') and profile.get('clothing_sizes'):
        values['clothing_sizes']=profile['clothing_sizes']
    return values


def assess(topic, card, profile):
    """'pass' | 'unknown' | 'exclude' | 'none' (the profile does not apply to this item)."""
    wanted=preferences(topic,profile)
    category=card.get('category')
    if not wanted or category not in ('clothing','footwear'):
        return NONE
    if category=='footwear' and 'shoe_size_eu' not in wanted or category=='clothing' and 'clothing_sizes' not in wanted:
        return NONE
    # The profile describes an adult man: kids' and women's items never fit.
    if card.get('gender')=='kids':
        return {'status':'exclude','reason':'Capo o scarpa da bambino: non adatto alle tue taglie.'}
    if card.get('gender')=='women':
        return {'status':'exclude','reason':'Articolo da donna: il profilo cerca capi da uomo o unisex.'}
    if category=='footwear':
        size,target=card.get('shoe_size_eu'),wanted['shoe_size_eu']
        if size is None:
            declared=f' (indicata: {card["size"]})' if card.get('size') else ''
            return {'status':'unknown','reason':f'Taglia EU delle scarpe non verificata{declared}; cerchi EU {target:g}.'}
        if size==target:
            return {'status':'pass','reason':f'Taglia EU {size:g}, compatibile.'}
        if abs(size-target)<=0.5:
            return {'status':'unknown','reason':f'Taglia EU {size:g} vicina alla tua (EU {target:g}): controlla la calzata.'}
        return {'status':'exclude','reason':f'Taglia EU {size:g}; nel tuo profilo cerchi EU {target:g}.'}
    size,targets=card.get('clothing_size'),wanted['clothing_sizes']
    if size is None:
        declared=f' (indicata: {card["size"]})' if card.get('size') else ''
        return {'status':'unknown','reason':f'Taglia del capo non verificata{declared}; cerchi {", ".join(targets)}.'}
    if size in targets:
        return {'status':'pass','reason':f'Taglia {size}, compatibile.'}
    if any(abs(CLOTHING_SIZES.index(size)-CLOTHING_SIZES.index(t))==1 for t in targets):
        return {'status':'unknown','reason':f'Taglia {size} vicina alle tue ({", ".join(targets)}): controlla le misure.'}
    return {'status':'exclude','reason':f'Taglia {size}; nel tuo profilo cerchi {", ".join(targets)}.'}
