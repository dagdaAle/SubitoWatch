"""Apply declared sizes without inferring EU/UK conversions or body measurements."""
import re

VERSION = 'sizes-3'

SHOES = re.compile(r'\b(scarp\w*|sneakers?|stival\w*|sandal\w*|ciabatt\w*|calzatur\w*|old\s+skool|sk8)\b',re.I)
CLOTHES = re.compile(r'\b(t[ -]?shirts?|tee|shirt|hemd|magliett\w*|maglia|polo|canott\w*|felp\w*|hoodie|sweat\w*|giacc\w*|giubbott\w*|jacket|veste|cazadora|chaqueta|gilet|smanicat\w*|pantalon\w*|jeans|chino|cargo|piumin\w*|fleece|polaire|camici\w*|camiseta|sudadera|bermuda|shorts|maglion\w*|pullover|cappell\w*|berrett\w*|beanie|cap|m[uü]tze)\b',re.I)
# Kids and women-only items never fit the profile; decided on the title alone, without AI.
KIDS = re.compile(r'\b(bambin\w*|bimb\w*|kids?|junior|b[ée]b[ée]|enfants?|kinder\w*|ni[ñn][oa]s?|menin[oa]|infant\w*)\b',re.I)
WOMEN = re.compile(r'\b(donna|femme|women\'?s?|woman|damen|mujer|lady|ladies)\b',re.I)
MEN_OR_UNISEX = re.compile(r'\b(uomo|homme|men\'?s?|man|herren|hombre|unisex)\b',re.I)
ORDER = ['XXS','XS','S','M','L','XL','XXL','3XL','4XL','5XL']
LETTERS = r'(?:5XL|4XL|3XL|XXXL|XXL|XXS|XL|XS|S|M|L)'
SIZE_LABEL = r'\b(?:taglia|taglie|tg\.?|size|misura|numero|num\.?|n\.|n°|taille|talla|gr[öo]ß?e|gr[öo]sse|maat|tamanho)\s*[:.\-]?\s*'


def preferences(topic, profile):
    scope=topic.get('profile_scope','none')
    values={}
    if scope in ('fashion','footwear') and profile.get('shoe_size_eu') is not None:
        values['shoe_size_eu']=profile['shoe_size_eu']
    if scope in ('fashion','clothing') and profile.get('clothing_sizes'):
        values['clothing_sizes']=profile['clothing_sizes']
    return values


def garment(topic, listing):
    """True when the title names a garment or shoe the topic's scope covers."""
    scope=topic.get('profile_scope','none'); title=listing['title']
    return bool((scope in ('fashion','clothing') and CLOTHES.search(title)) or (scope in ('fashion','footwear') and SHOES.search(title)))


def assess(topic, listing):
    profile=topic.get('buyer_profile') or {}
    if not profile or topic.get('profile_scope','none')=='none':return {'status':'none','reason':''}
    title=listing['title']; text=title+'\n'+listing.get('description','')
    if KIDS.search(title):return {'status':'exclude','reason':'Capo o scarpa da bambino: non adatto alle tue taglie.'}
    if WOMEN.search(title) and not MEN_OR_UNISEX.search(title):return {'status':'exclude','reason':'Articolo da donna: il profilo cerca capi da uomo o unisex.'}
    scope=topic.get('profile_scope','none')
    shoe=bool(SHOES.search(text)); clothing=bool(CLOTHES.search(text))
    category = 'footwear' if scope=='footwear' else 'clothing' if scope=='clothing' else ('footwear' if shoe and not clothing else 'clothing' if clothing and not shoe else None)
    if category=='footwear' and profile.get('shoe_size_eu') is None:return {'status':'none','reason':''}
    if category=='clothing' and not profile.get('clothing_sizes'):return {'status':'none','reason':''}
    if category=='footwear' and 'shoe_size_eu' in profile:
        found=[]
        pattern=rf'(?:{SIZE_LABEL}|\bEU\s*)({{number}}(?:\s*[/–-]\s*{{number}})?)'.replace('{number}',r'\d{2}(?:[.,]5)?')
        for match in re.finditer(pattern,text,re.I):
            # Explicit UK/US labels cannot be silently interpreted as EU.
            if re.search(r'\b(?:UK|US)\s*$',text[max(0,match.start()-6):match.start()],re.I):continue
            for value in re.findall(r'\d{2}(?:[.,]5)?',match.group(1)):
                size=float(value.replace(',','.'))
                if 15<=size<=55:found.append(size)
        wanted=profile['shoe_size_eu']
        if not found:return {'status':'unknown','reason':f'Taglia EU delle scarpe non verificata; cerchi EU {wanted:g}. Nessuna conversione UK/US automatica.'}
        if wanted in found:return {'status':'pass','reason':f'Taglia dichiarata compatibile con EU {wanted:g}.'}
        if any(abs(x-wanted)<=0.5 for x in found):return {'status':'unknown','reason':f'Taglia vicina alla tua (EU {wanted:g}): controlla la calzata del modello.'}
        return {'status':'exclude','reason':f'Taglie scarpe dichiarate: {", ".join(f"{x:g}" for x in sorted(set(found)))}. Nel tuo profilo cerchi EU {wanted:g}.'}
    if category=='clothing' and profile.get('clothing_sizes'):
        aliases={'extra extra large':'XXL','extra large':'XL','extra small':'XS','small':'S','medium':'M','large':'L'}
        def normalized(value):
            for label,size in aliases.items():value=re.sub(r'\b'+label+r'\b',size,value,flags=re.I)
            return value
        found=[m.group(1).upper() for m in re.finditer(SIZE_LABEL+rf'({LETTERS}(?:\s*[/–-]\s*{LETTERS})*)(?!\w)',normalized(text),re.I)]
        # A bare letter in the title is a size only next to a garment word ("Duffel M" is a bag).
        if CLOTHES.search(title):found += re.findall(rf'(?<![\w])({LETTERS})(?![\w\x27’])',normalized(title))
        sizes={v for part in found for v in re.findall(LETTERS,part)}
        sizes={'3XL' if v=='XXXL' else v for v in sizes}
        wanted=set(profile['clothing_sizes'])
        if not sizes:return {'status':'unknown','reason':'Taglia del capo non verificata; cerchi '+', '.join(profile['clothing_sizes'])+'. Le taglie numeriche non vengono convertite senza dati del marchio.'}
        if sizes & wanted:return {'status':'pass','reason':'Taglia dichiarata compatibile con il profilo: '+', '.join(sorted(sizes & wanted))+'.'}
        near=[ORDER.index(v) for v in wanted if v in ORDER]
        if any(abs(ORDER.index(v)-i)==1 for v in sizes if v in ORDER for i in near):
            return {'status':'unknown','reason':'Taglia '+', '.join(sorted(sizes))+' vicina alle tue ('+', '.join(profile['clothing_sizes'])+'): controlla le misure, alcuni modelli vestono diversi.'}
        return {'status':'exclude','reason':'Taglie abbigliamento dichiarate: '+', '.join(sorted(sizes))+'. Nel tuo profilo cerchi '+', '.join(profile['clothing_sizes'])+'.'}
    return {'status':'unknown','reason':'Tipo di capo o taglia non verificati: controlla la compatibilità con le tue preferenze personali.'}


def annotate(body, verdict):
    body['size_check']=verdict
    if verdict['status']=='unknown' and not body.get('requirement_failures'):
        body['requirement_unknowns']=list(dict.fromkeys([*body.get('requirement_unknowns',[]),verdict['reason']]))
    return body


def refine(topic, listing, analysis):
    """Use photo evidence for object type, but only seller text for the size."""
    if topic.get('profile_scope')!='fashion' or not topic.get('buyer_profile'):
        return analysis
    original=assess(topic,listing)
    if original['status']!='unknown' or not analysis.get('images_examined') or analysis.get('confidence',0)<70:
        return analysis
    evidence=' '.join(o.get('claim','')+' '+o.get('detail','') for o in analysis.get('observations',[]) if o.get('basis')=='image')
    shoe=bool(SHOES.search(evidence));clothing=bool(CLOTHES.search(evidence))
    if shoe==clothing:return analysis
    verdict=assess({**topic,'profile_scope':'footwear' if shoe else 'clothing'},listing)
    if verdict['status']=='unknown':return analysis
    body={**analysis,'size_check':verdict}
    old_reason=(analysis.get('size_check') or original)['reason']
    body['requirement_unknowns']=[value for value in analysis.get('requirement_unknowns',[]) if value!=old_reason]
    if verdict['status']=='exclude':
        body['relevance']=0
        body['requirement_failures']=list(dict.fromkeys([*analysis.get('requirement_failures',[]),verdict['reason']]))
        body['model_reason']=analysis['reason']
        body['reason']=verdict['reason']
    return body
