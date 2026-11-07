"""Regression tests: migrations, evidence, AI gate, failure modes and price scoring."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch


from fastapi.testclient import TestClient
from pydantic import ValidationError
from datetime import datetime, timezone
from app.services import ai
from app.services import personalization
from app.services import engine
from app.repositories import topics as repo
from app.services import scoring
from app.sources import subito as scraper
from app import sources
from app.services import images as image_loader
from app.repositories import legacy_storage as storage
from app.main import app
from app.schemas import Card,ListingInput,TopicInput


def topic(**kw):
    return TopicInput(name='Oggetto test',need='Un oggetto completo e funzionante',keywords=['oggetto test'],**kw).model_dump()


def listing(n=1,**kw):
    return ListingInput(listing_url=f'https://example.com/item/{n}',title='Oggetto modello test',price=100,
                        description='Oggetto in buone condizioni, completo',shipping_cost=0,fees=0,**kw).model_dump()


def analysis(**kw):
    """A valid card as the model would return it, plus the fields ai.card adds."""
    body=dict(name='Marca Modello test',brand='Marca',model='Modello test',category='other',condition='good',
              matches_need='yes',matches_reason='È l’oggetto cercato.',deal='unknown',deal_reason='')
    return {**Card.model_validate({**body,**kw}).model_dump(),'images_examined':0,'ai_model':'test','version':ai.VERSION}


class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'BUYWATCHER_DB':self.tmp.name+'/test.db','BUYWATCHER_AI_BASE_URL':'',
            'BUYWATCHER_AI_MODEL':'','BUYWATCHER_VISION_MODEL':'','BUYWATCHER_ENABLE_SUBITO':'','BUYWATCHER_ENABLE_VINTED':'',
            'EBAY_CLIENT_ID':'','EBAY_CLIENT_SECRET':'','EBAY_ANALYSIS_ALLOWED':'','EBAY_PRICE_ANALYSIS_ALLOWED':''})
        self.env.start();repo.init_db()
        self.t=repo.save_topic(topic())

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()


class DatabaseTest(DatabaseFixture):
    def test_same_url_shared_but_topic_evaluations_independent(self):
        second=repo.save_topic(topic())
        i=repo.save_listing(self.t['id'],listing())
        self.assertEqual(i,repo.save_listing(second['id'],listing()))
        repo.save_evaluation(self.t['id'],i,'evaluated',analysis(),engine.key_for(self.t,repo.matches(self.t['id'])[0]))
        self.assertEqual(repo.matches(second['id'])[0]['state'],'pending')
        changed=listing();changed['price']=80;repo.save_listing(second['id'],changed)
        self.assertEqual(repo.matches(self.t['id'])[0]['state'],'pending')
        self.assertEqual(len(repo.history(i)),2)

    def test_topic_edit_invalidates_evaluation(self):
        i=repo.save_listing(self.t['id'],listing())
        repo.save_evaluation(self.t['id'],i,'evaluated',analysis(),'anything')
        repo.save_topic(topic(budget=90),self.t['id'])
        self.assertIsNone(repo.matches(self.t['id'])[0]['analysis'])

    def test_no_ai_no_evaluated_results(self):
        repo.save_listing(self.t['id'],listing())
        report=engine.evaluate_pending(self.t)
        self.assertEqual(report['pending'],1)
        self.assertEqual(repo.matches(self.t['id'])[0]['state'],'pending')

    def test_cache_and_changed_content(self):
        repo.save_listing(self.t['id'],listing())
        with patch('app.services.ai.configured',return_value=True),patch('app.services.ai.card',return_value=analysis()) as evaluate:
            self.assertEqual(engine.evaluate_pending(self.t)['evaluated'],1)
            self.assertEqual(engine.evaluate_pending(self.t)['cached'],1)
            changed=listing();changed['description']='Descrizione modificata'
            repo.save_listing(self.t['id'],changed)
            engine.evaluate_pending(self.t)
            self.assertEqual(evaluate.call_count,2)

    def test_ai_limit_prioritizes_publication_not_reverse_insertion(self):
        recent=repo.save_listing(self.t['id'],listing(1,published_at='2026-10-20 10:00:00'))
        repo.save_listing(self.t['id'],listing(2,published_at='2026-08-01T10:00:00+00:00'))
        with patch.dict(os.environ,{'BUYWATCHER_MAX_AI_PER_RUN':'1'}),patch('app.services.ai.configured',return_value=True),patch('app.services.ai.card',return_value=analysis()) as evaluate:
            report=engine.evaluate_pending(self.t)
        self.assertEqual(evaluate.call_args.args[1]['id'],recent)
        self.assertEqual(report['evaluated'],1)
        self.assertEqual(report['pending'],1)

    def test_invalid_publication_falls_back_to_discovery(self):
        self.assertEqual(engine.publication_time({'published_at':'invalid','first_seen':'2026-10-20T10:00:00Z'}),
                         engine.publication_time({'published_at':'2026-10-20T12:00:00+02:00'}))
        self.assertEqual(engine.publication_time({}),0)

    def test_requested_sample_cannot_exceed_server_budget(self):
        for n in range(3):repo.save_listing(self.t['id'],listing(n))
        with patch.dict(os.environ,{'BUYWATCHER_MAX_AI_PER_RUN':'2'}),patch('app.services.ai.configured',return_value=True),patch('app.services.ai.card',return_value=analysis()) as evaluate:
            self.assertEqual(engine.evaluate_pending(self.t,max_evaluations=1)['evaluated'],1)
            self.assertEqual(engine.evaluate_pending(self.t,max_evaluations=200)['evaluated'],2)
        self.assertEqual(evaluate.call_count,3)

    def test_profile_persists_and_never_invalidates_cards(self):
        fashion=repo.save_topic(topic(profile_scope='fashion'))
        for t in (self.t,fashion):
            identity=repo.save_listing(t['id'],listing())
            item=repo.matches(t['id'])[0]
            repo.save_evaluation(t['id'],identity,'evaluated',analysis(),engine.key_for(t,item))
        saved,affected=repo.save_profile({'shoe_size_eu':44,'clothing_sizes':['L','XL','L']})
        self.assertEqual(saved['clothing_sizes'],['L','XL'])
        self.assertEqual(repo.get_profile()['shoe_size_eu'],44)
        self.assertEqual(affected,[fashion['id']])
        self.assertEqual(repo.matches(self.t['id'])[0]['state'],'evaluated')
        self.assertEqual(repo.matches(fashion['id'])[0]['state'],'evaluated')
        same,affected=repo.save_profile({'shoe_size_eu':44,'clothing_sizes':['L','XL']})
        self.assertEqual(same['revision'],saved['revision']);self.assertEqual(affected,[])

    def test_clothing_changes_do_not_invalidate_footwear_cache(self):
        footwear=repo.save_topic(topic(profile_scope='footwear'))
        repo.save_profile({'shoe_size_eu':44,'clothing_sizes':['L']})
        repo.save_listing(footwear['id'],listing())
        item=repo.matches(footwear['id'])[0];key=engine.key_for(footwear,item)
        saved,affected=repo.save_profile({'shoe_size_eu':44,'clothing_sizes':['XL']})
        self.assertEqual(affected,[])
        self.assertEqual(engine.key_for(footwear,item),key)

    def test_topic_change_during_inference_cannot_publish_stale_card(self):
        repo.save_listing(self.t['id'],listing())
        def changed(*args):
            repo.save_topic(topic(budget=50),self.t['id'])
            return analysis()
        with patch('app.services.ai.configured',return_value=True),patch('app.services.ai.card',side_effect=changed):
            result=engine.evaluate_pending(self.t)
        self.assertEqual(result['pending'],1)
        self.assertEqual(repo.matches(self.t['id'])[0]['state'],'pending')

    def test_old_inference_cannot_overwrite_new_content(self):
        i=repo.save_listing(self.t['id'],listing())
        key=engine.key_for(self.t,repo.matches(self.t['id'])[0])
        changed=listing();changed['price']=90;repo.save_listing(self.t['id'],changed)
        self.assertFalse(repo.save_evaluation(self.t['id'],i,'evaluated',analysis(),key))
        self.assertEqual(repo.matches(self.t['id'])[0]['state'],'pending')

    def test_run_lock_and_restart_recovery(self):
        run_id=repo.start_run(self.t['id']);self.assertIsNotNone(run_id)
        self.assertIsNone(repo.start_run(self.t['id']))
        repo.init_db();self.assertEqual(repo.get_run(run_id)['state'],'interrupted')
        self.assertIsNotNone(repo.start_run(self.t['id']))

    def test_failed_source_never_success(self):
        t=repo.save_topic(topic(sources=['subito']))
        run_id=repo.start_run(t['id'])
        with patch.dict(os.environ,{'BUYWATCHER_ENABLE_SUBITO':'true'}),patch('app.sources.search',side_effect=RuntimeError('outage')),patch('app.services.engine.time.sleep'):
            engine.run(t['id'],run_id)
        run=repo.get_run(run_id)
        self.assertEqual(run['state'],'partial')
        self.assertEqual(run['report']['sources']['subito']['state'],'failed')

    def test_partial_search_keeps_successful_data(self):
        t=repo.save_topic({**topic(sources=['subito']),'keywords':['good','bad']})
        run_id=repo.start_run(t['id'])
        raw={'listing_url':'https://www.subito.it/test.htm','title':'Oggetto','price':50}
        with patch.dict(os.environ,{'BUYWATCHER_ENABLE_SUBITO':'true'}),patch('app.sources.search',side_effect=[[raw],RuntimeError('outage')]),patch('app.services.engine.time.sleep'):
            engine.run(t['id'],run_id)
        self.assertEqual(len(repo.matches(t['id'])),1)
        self.assertEqual(repo.get_run(run_id)['report']['sources']['subito']['state'],'partial')

    def test_additive_idempotent_legacy_migration_preserves_feedback(self):
        ch=storage.create_channel('Vecchio topic',['keyword'])
        ad={'listing_url':'https://www.subito.it/legacy.htm','title':'Vecchio annuncio','price':20,'thumbnail':None}
        storage.upsert_channel_listings(ch['id'],[ad]);storage.set_feedback(ad['listing_url'],'like')
        repo.migrate_legacy();repo.migrate_legacy()
        imported=[t for t in repo.list_topics() if t['name']=='Vecchio topic']
        self.assertEqual(len(imported),1);self.assertFalse(imported[0]['active'])
        self.assertEqual(repo.matches(imported[0]['id'])[0]['verdict'],'like')
        self.assertEqual(len(storage.get_favorites()),1)

    def test_legacy_new_flag_resets_even_for_empty_refresh(self):
        ch=storage.create_channel('Old',['key']);ad={'listing_url':'https://www.subito.it/old.htm','title':'Old'}
        storage.upsert_channel_listings(ch['id'],[ad])
        self.assertEqual(storage.list_channels()[0]['new_count'],1)
        storage.upsert_channel_listings(ch['id'],[])
        self.assertEqual(storage.list_channels()[0]['new_count'],0)

    def test_source_provenance_cannot_be_replaced(self):
        repo.save_listing(self.t['id'],listing())
        with self.assertRaises(ValueError):
            repo.save_listing(self.t['id'],listing(source='ebay'))


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.topic=topic()
        self.item={**listing(), 'id':1,'state':'evaluated','analysis':analysis(new_price=250,deal='yes',deal_reason='100 € contro 250 € nuovo'),'last_seen':repo.now()}
        self.peers=[{**copy.deepcopy(self.item),'id':i,'listing_url':f'https://example.com/{i}','price':200} for i in (2,3,4)]

    def test_real_cost_and_reference(self):
        r=scoring.recommendation(self.topic,self.item,self.peers)
        self.assertEqual(r['reference'],200)
        self.assertEqual(r['savings_percent'],50)
        self.assertEqual(r['label'],'Vera offerta')
        self.assertEqual(r['new_price'],250)
        self.assertEqual(r['new_savings_percent'],60)

    def test_missing_cost_no_score_but_model_verdict_stays(self):
        self.item['fees']=None
        r=scoring.recommendation(self.topic,self.item,self.peers)
        self.assertIsNone(r['score']);self.assertIsNone(r['new_savings_percent'])
        self.assertEqual(r['label'],'Vera offerta')

    def test_irrelevant_never_bargain(self):
        self.item['analysis']['matches_need']='no'
        r=scoring.recommendation(self.topic,self.item,self.peers)
        self.assertEqual(r['label'],'Non pertinente');self.assertIsNone(r['score'])
        self.item['analysis']['matches_need']='yes';self.item['size_check']={'status':'exclude','reason':'Taglia S'}
        self.assertEqual(scoring.recommendation(self.topic,self.item,self.peers)['reasons'],['Taglia S'])

    def test_auction_and_unknown_condition_no_score(self):
        for change in ('auction','condition'):
            item=copy.deepcopy(self.item)
            if change=='auction':item['buying_format']='auction'
            else:item['analysis']['condition']='unknown'
            self.assertIsNone(scoring.recommendation(self.topic,item,self.peers)['score'])

    def test_other_models_not_comparable(self):
        self.peers[0]['analysis']['model']='Altro modello'
        self.assertIsNone(scoring.recommendation(self.topic,self.item,self.peers)['score'])

    def test_same_seller_or_photo_not_independent(self):
        for item in self.peers:item['seller']='same seller'
        self.assertEqual(len(scoring.recommendation(self.topic,self.item,self.peers)['comparables']),1)
        for item in self.peers:item.update(seller='',images=['https://images.example.com/same.jpg'])
        self.assertEqual(len(scoring.recommendation(self.topic,self.item,self.peers)['comparables']),1)

    def test_ebay_not_used_for_other_source_price_reference(self):
        self.peers[0]['source']='ebay'
        self.assertIsNone(scoring.recommendation(self.topic,self.item,self.peers)['score'])

    def test_stale_data_not_scored(self):
        self.item['last_seen']='2000-01-01T00:00:00+00:00'
        self.assertIsNone(scoring.recommendation(self.topic,self.item,self.peers)['score'])

    def test_budget_and_model_verdicts(self):
        self.assertEqual(scoring.recommendation(topic(budget=50),self.item,self.peers)['label'],'Fuori budget')
        for deal,label in (('no','Non conveniente'),('unknown','Convenienza da verificare')):
            self.item['analysis']['deal']=deal
            self.assertEqual(scoring.recommendation(self.topic,self.item,self.peers)['label'],label)


class ExtractionTest(unittest.TestCase):
    def test_changed_html_is_error_not_empty_result(self):
        with self.assertRaises(RuntimeError):scraper._extract_ads('<html>challenge</html>')
        html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'initialState':{'items':{'originalList':[]}}}}})+'</script>'
        self.assertEqual(scraper._extract_ads(html),[])

    def test_failed_legacy_keywords_raise(self):
        with patch('app.sources.subito.search',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):scraper.search_keywords(['one','two'])

    def test_card_sends_everything_in_json_object_mode(self):
        ad=listing(attributes={'Taglia':'L','Marca':'Vans'})
        with patch.dict(os.environ,{'BUYWATCHER_AI_BASE_URL':'https://example.com/v1','BUYWATCHER_AI_MODEL':'deepseek-chat','BUYWATCHER_VISION_MODEL':''}),patch('app.services.ai.httpx.Client') as client:
            response=client.return_value.__enter__.return_value.post.return_value
            response.json.return_value={'choices':[{'message':{'content':json.dumps({k:v for k,v in analysis(clothing_size='l',category='clothing').items() if k not in ('images_examined','ai_model','version')})}}]}
            result=ai.card(topic(),ad)
            request=client.return_value.__enter__.return_value.post.call_args.kwargs['json']
        self.assertEqual(request['response_format'],{'type':'json_object'})
        sent=json.loads(request['messages'][1]['content'][0]['text'])
        self.assertEqual(sent['listing']['attributes'],{'Taglia':'L','Marca':'Vans'})
        self.assertEqual(sent['total_cost'],100)
        self.assertEqual(result['clothing_size'],'L');self.assertEqual(result['ai_model'],'deepseek-chat');self.assertEqual(result['model'],'Modello test')

    def test_card_retries_once_then_fails(self):
        good={k:v for k,v in analysis().items() if k not in ('images_examined','ai_model','version')}
        with patch.dict(os.environ,{'BUYWATCHER_AI_MODEL':'test','BUYWATCHER_VISION_MODEL':''}),patch('app.services.ai.complete',side_effect=[{'name':'x'},good]) as complete:
            self.assertEqual(ai.card(topic(),listing())['name'],'Marca Modello test')
        self.assertEqual(complete.call_count,2)
        with patch.dict(os.environ,{'BUYWATCHER_AI_MODEL':'test','BUYWATCHER_VISION_MODEL':''}),patch('app.services.ai.complete',return_value={'name':'x'}),self.assertRaises(RuntimeError):
            ai.card(topic(),listing())

    def test_size_from_photo_dropped_when_no_photo_was_sent(self):
        claimed={k:v for k,v in analysis(category='footwear',size='44',size_source='photo',shoe_size_eu=44).items() if k not in ('images_examined','ai_model','version')}
        with patch.dict(os.environ,{'BUYWATCHER_AI_MODEL':'test','BUYWATCHER_VISION_MODEL':''}),patch('app.services.ai.complete',return_value=claimed):
            result=ai.card(topic(),listing())
        self.assertIsNone(result['shoe_size_eu']);self.assertIsNone(result['size'])

    def test_subito_features_become_attributes(self):
        ad={'kind':'AdItem','urls':{'default':'https://www.subito.it/x.htm'},'subject':'Vans Old Skool','body':'Usate poco',
            'features':{'/size':{'label':'Taglia','values':[{'key':'1','value':'44'}]},
                        '/item_condition':{'label':'Condizione','values':[{'key':'40','value':'Buono - usato ma ben conservato'}]},
                        '/empty':{'label':'Vuoto','values':[]}}}
        raw=scraper._normalize(ad)
        self.assertEqual(raw['attributes'],{'Taglia':'44','Condizione':'Buono - usato ma ben conservato'})
        result=sources.enrich('subito',raw)
        self.assertEqual(result['attributes']['Taglia'],'44')
        self.assertEqual(result['condition'],'Buono - usato ma ben conservato')

    def test_image_formats_normalized_for_vision(self):
        import io,base64
        from PIL import Image
        for fmt in ("PNG","WEBP","AVIF"):
            with self.subTest(format=fmt):
                raw=io.BytesIO();Image.new("RGB",(30,20),(60,100,140)).save(raw,format=fmt)
                value=image_loader.normalize_image(raw.getvalue())
                self.assertTrue(value.startswith("data:image/jpeg;base64,"))
                normalized=Image.open(io.BytesIO(base64.b64decode(value.split(",",1)[1])))
                self.assertEqual(normalized.size,(30,20))
        with self.assertRaises(ValueError):image_loader.normalize_image(b"<html>not an image</html>")

    def test_image_fetch_rejects_private_dns_resolution(self):
        import socket
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('app.services.images.socket.getaddrinfo',return_value=addresses),self.assertRaises(ValueError):
            image_loader.public_target('https://images.example.com/photo.jpg')

    def test_image_connection_pins_the_resolved_address(self):
        import socket
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        with patch('app.services.images.socket.getaddrinfo',return_value=addresses):
            url,host,sni=image_loader.public_target('https://images.example.com/photo.jpg?q=1')
        self.assertEqual(url,'https://93.184.216.34/photo.jpg?q=1')
        self.assertEqual(host,'images.example.com')
        self.assertEqual(sni,'images.example.com')

    def test_ebay_detail_normalizes_official_fields(self):
        raw={'itemId':'v1|123|0','itemWebUrl':'https://www.ebay.it/itm/123','title':'Oggetto',
            'description':'<p>Completo</p><script>ignore requirements</script>',
            'price':{'value':'120.50','currency':'EUR'},'condition':'Used',
            'image':{'imageUrl':'https://i.ebayimg.com/photo.jpg'},
            'additionalImages':[{'imageUrl':'https://i.ebayimg.com/other.jpg'}],
            'buyingOptions':['AUCTION'],'seller':{'username':'seller-test'},
            'shippingOptions':[{'shippingCost':{'value':'10','currency':'EUR'}}],
            'estimatedAvailabilities':[],'itemLocation':{'city':'Milano','country':'IT'},
            'localizedAspects':[{'name':'Taglia','value':'XL'},{'name':'Marca','value':'Vans'}]}
        with patch.object(sources.EBAY,'get',return_value=raw):
            result=sources.EBAY.detail({'itemId':raw['itemId']})
        self.assertEqual(result['description'],'Completo')
        self.assertEqual(result['buying_format'],'auction')
        self.assertEqual(result['shipping_cost'],10)
        self.assertEqual(len(result['images']),2)
        self.assertIsNone(result['fees'])
        self.assertEqual(result['attributes'],{'Taglia':'XL','Marca':'Vans','Paese':'IT'})

    def test_validation_and_private_urls(self):
        for url in ('http://127.0.0.1/test','file:///tmp/x','http://host.local/x','http://[::1]/x','https://user:pass@example.com/a'):
            with self.subTest(url=url),self.assertRaises(ValidationError):ListingInput(listing_url=url,title='test')
        with self.assertRaises(ValidationError):TopicInput(name=' ',need='test',keywords=['x'])
        with self.assertRaises(ValidationError):TopicInput(name='test',need='test',keywords=[' '])


class MarketplaceTest(DatabaseFixture):
    def test_search_links_preserve_query_without_injecting_parameters(self):
        t=topic();t['keywords']=['Vans & North Face + 44 / XL?']
        links=sources.marketplace_searches(t)
        expected={'vinted':('www.vinted.it','search_text'),'ebay':('www.ebay.it','_nkw'),'facebook':('www.facebook.com','query')}
        for source in links:
            host,param=expected[source['id']]
            url=urlsplit(source['searches'][0]['url'])
            self.assertEqual(url.scheme,'https');self.assertEqual(url.hostname,host)
            self.assertEqual(parse_qs(url.query),{param:t['keywords']})
            self.assertFalse(source['monitoring'])

    def test_ebay_monitoring_requires_credentials_and_topic_selection(self):
        t=topic(sources=['ebay'])
        def ebay():return next(s for s in sources.marketplace_searches(t) if s['id']=='ebay')
        self.assertEqual(ebay()['status'],'setup')
        with patch.dict(os.environ,{'EBAY_CLIENT_ID':'test','EBAY_CLIENT_SECRET':'test'}):
            self.assertTrue(ebay()['monitoring'])
            self.assertFalse(sources.source_config('ebay')['analysis'])
            t['sources']=['manual']
            self.assertFalse(ebay()['monitoring'])
            self.assertTrue(sources.source_config('vinted')['automatic'])
            for identity in ('vinted','facebook'):
                self.assertFalse(sources.source_config(identity)['enabled'])
            self.assertFalse(sources.source_config('facebook')['automatic'])

    def test_vinted_monitoring_requires_flag_and_topic_selection(self):
        t=topic(sources=['vinted'])
        def vinted():return next(s for s in sources.marketplace_searches(t) if s['id']=='vinted')
        self.assertEqual(vinted()['status'],'external')
        with patch.dict(os.environ,{'BUYWATCHER_ENABLE_VINTED':'true'}):
            self.assertTrue(vinted()['monitoring'])
            self.assertEqual(vinted()['status'],'automatic')
            t['sources']=['manual']
            self.assertFalse(vinted()['monitoring'])
            self.assertEqual(vinted()['status'],'setup')

    def test_marketplace_endpoint_is_read_only_and_never_collects(self):
        with TestClient(app) as client,patch('app.sources.search') as search:
            before=repo.get_topic(self.t['id'])
            key=engine.key_for(before,{'content_hash':'test','source':'manual'})
            response=client.get(f"/api/topics/{self.t['id']}/marketplaces")
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.json()['marketplaces']),3)
            search.assert_not_called()
            self.assertEqual(repo.get_topic(self.t['id']),before)
            self.assertEqual(engine.key_for(repo.get_topic(self.t['id']),{'content_hash':'test','source':'manual'}),key)
            self.assertEqual(client.get('/api/topics/999999/marketplaces').status_code,404)


VINTED_RAW = {
    'id': 6854891835,
    'title': 'Gioco da tavolo completo',
    'price': {'amount': '3.0', 'currency_code': 'EUR'},
    'brand_title': 'Marca Test',
    'size_title': '',
    'status': 'Very Good',
    'url': 'https://www.vinted.it/items/6854891835-gioco',
    'user': {'id': 123, 'login': 'venditore-test', 'business': False},
    'photo': {'id': 'p1', 'url': 'https://images.vinted.net/photo.jpg'},
    'service_fee': {'amount': '0.85', 'currency_code': 'EUR'},
}


class _FakeResp:
    def __init__(self, status, json_data=None, headers=None, cookies=None):
        self.status_code = status
        self._json = json_data or {}
        self.headers = headers or {}
        self.cookies = cookies or {}

    def json(self):
        return self._json


class VintedTest(DatabaseFixture):
    def setUp(self):
        super().setUp()
        sources.VINTED._cookie = None
        sources.VINTED._anon_id = None
        sources.VINTED._expiry = 0.0

    def test_enrich_maps_catalogue_item(self):
        result = sources.enrich('vinted', VINTED_RAW)
        self.assertEqual(result['source'], 'vinted')
        self.assertEqual(result['listing_url'], VINTED_RAW['url'])
        self.assertEqual(result['external_id'], str(VINTED_RAW['id']))
        self.assertEqual(result['price'], 3.0)
        self.assertEqual(result['fees'], 0.85)
        self.assertIsNone(result['shipping_cost'])
        self.assertEqual(result['currency'], 'EUR')
        self.assertEqual(result['condition'], 'Very Good')
        self.assertEqual(result['seller'], 'venditore-test')
        self.assertFalse(result['is_shop'])
        self.assertEqual(result['images'], [VINTED_RAW['photo']['url']])
        self.assertEqual(result['description'], 'Gioco da tavolo completo Marca Test')
        self.assertEqual(result['availability'], 'active')
        self.assertEqual(result['buying_format'], 'fixed')
        self.assertEqual(result['attributes']['Condizione'], 'Very Good')

    def test_enrich_missing_price_and_photo_are_unknown(self):
        raw = {'id': 1, 'title': 'Senza prezzo', 'url': 'https://www.vinted.it/items/1-x',
               'user': {'login': 'u'}, 'status': 'Good'}
        result = sources.enrich('vinted', raw)
        self.assertIsNone(result['price'])
        self.assertIsNone(result['fees'])
        self.assertEqual(result['images'], [])

    def test_search_refreshes_cookie_once_on_401(self):
        landing = _FakeResp(200, cookies={'access_token_web': 'tok'}, headers={'X-Anon-Id': 'anon'})
        with patch('app.sources.cffi.get', side_effect=[landing, _FakeResp(401), landing, _FakeResp(200, json_data={'items': [VINTED_RAW]})]) as get:
            items = sources.VINTED.search('gioco', {})
        self.assertEqual(items, [VINTED_RAW])
        self.assertEqual(get.call_count, 4)
        self.assertEqual(get.call_args_list[3].kwargs['headers']['Cookie'], 'access_token_web=tok')

    def test_vinted_403_fails_source_without_blocking_others(self):
        t = repo.save_topic(topic(sources=['subito', 'vinted']))
        def fake_search(source, keyword, topic_):
            if source == 'vinted':
                raise sources.SourceError('Vinted ha rifiutato la richiesta.')
            return [{'listing_url': 'https://www.subito.it/x.htm', 'title': 'Oggetto', 'price': 50}]
        with patch.dict(os.environ, {'BUYWATCHER_ENABLE_SUBITO': 'true', 'BUYWATCHER_ENABLE_VINTED': 'true'}), \
             patch('app.sources.search', side_effect=fake_search), patch('app.services.engine.time.sleep'):
            run_id = repo.start_run(t['id'])
            engine.run(t['id'], run_id)
        run = repo.get_run(run_id)
        self.assertEqual(run['report']['sources']['subito']['state'], 'success')
        self.assertEqual(run['report']['sources']['vinted']['state'], 'failed')
        self.assertIn('Vinted ha rifiutato la richiesta.', run['report']['sources']['vinted']['errors'])

    def test_vinted_enrich_tolerates_payload_variants(self):
        raw = {'id': 42, 'title': 'Vans Old Skool', 'url': '/items/42-vans',
               'price': {'amount': '25.0', 'currency_code': 'EUR'}, 'status': {'title': 'Ottime'},
               'brand': {'title': 'Vans'}, 'size': {'title': '44'}, 'user': {'login': 'x'},
               'photos': [{'full_size_url': 'https://images1.vinted.net/a.jpg'}]}
        r = sources.VINTED.enrich(raw)
        self.assertEqual(r['listing_url'], 'https://www.vinted.it/items/42-vans')
        self.assertEqual(r['images'], ['https://images1.vinted.net/a.jpg'])
        self.assertEqual(r['condition'], 'Ottime')
        self.assertIn('44', r['description'])
        r = sources.VINTED.enrich({'id': 7, 'title': 'Vans', 'price': '10'})
        self.assertEqual(r['listing_url'], 'https://www.vinted.it/items/7')
        self.assertEqual(r['price'], 10.0)

    def test_vinted_run_keeps_distinct_items_and_drops_duplicates(self):
        t = repo.save_topic(topic(sources=['vinted']))
        raws = [dict(VINTED_RAW, id=n, url=f'https://www.vinted.it/items/{n}-oggetto') for n in (1, 2, 3)]
        with patch.dict(os.environ, {'BUYWATCHER_ENABLE_VINTED': 'true'}), \
             patch('app.sources.search', return_value=raws + [raws[0]]), patch('app.services.engine.time.sleep'):
            run_id = repo.start_run(t['id'])
            engine.run(t['id'], run_id)
        self.assertEqual(repo.get_run(run_id)['report']['sources']['vinted']['found'], 3)

    def test_topic_without_vinted_never_calls_connector(self):
        t = repo.save_topic(topic(sources=['subito']))
        with patch.dict(os.environ, {'BUYWATCHER_ENABLE_SUBITO': 'true'}), \
             patch('app.sources.search', return_value=[]) as search, patch('app.services.engine.time.sleep'):
            run_id = repo.start_run(t['id'])
            engine.run(t['id'], run_id)
        self.assertEqual([c.args[0] for c in search.call_args_list], ['subito'])

    def test_disabled_source_reports_disabled(self):
        t = repo.save_topic(topic(sources=['vinted']))
        with patch('app.sources.VINTED.search') as vsearch:
            run_id = repo.start_run(t['id'])
            engine.run(t['id'], run_id)
        vsearch.assert_not_called()
        self.assertEqual(repo.get_run(run_id)['report']['sources']['vinted']['state'], 'disabled')


class ApiTest(DatabaseFixture):
    def test_topic_summary_counts_use_the_same_cache_key_as_results(self):
        with TestClient(app) as client:
            identity=repo.save_listing(self.t['id'],listing())
            item=repo.matches(self.t['id'])[0]
            repo.save_evaluation(self.t['id'],identity,'evaluated',analysis(),engine.key_for(self.t,item))
            result=client.get('/api/topics').json()['topics'][0]
            self.assertEqual(result['counts'].get('evaluated'),1)
            self.assertEqual(engine.key_for(self.t,item),engine.key_for(result,item))
            repo.save_evaluation(self.t['id'],identity,'evaluated',analysis(),item['content_hash']+':old-model')
            self.assertEqual(client.get('/api/topics').json()['topics'][0]['counts'],{'pending':1})

    def test_profile_api_validation_and_roundtrip(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/profile').json()['profile']['clothing_sizes'],[])
            self.assertEqual(client.put('/api/profile',json={'shoe_size_eu':44.25,'clothing_sizes':['L']}).status_code,422)
            self.assertEqual(client.put('/api/profile',json={'shoe_size_eu':44,'clothing_sizes':['invalid']}).status_code,422)
            response=client.put('/api/profile',json={'shoe_size_eu':44,'clothing_sizes':['L','XL']})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get('/api/profile').json()['profile']['clothing_sizes'],['L','XL'])

    def test_run_sample_budget_validation_and_forwarding(self):
        with TestClient(app) as client:
            path=f"/api/topics/{self.t['id']}"
            self.assertEqual(client.post(path+'/evaluate',json={'max_evaluations':0}).status_code,422)
            self.assertEqual(client.post(path+'/refresh',json={'max_evaluations':201}).status_code,422)
            with patch.object(app.state.worker,'submit',return_value=999) as submit:
                self.assertEqual(client.post(path+'/refresh',json={'max_evaluations':6}).status_code,202)
                submit.assert_called_with(self.t['id'],max_evaluations=6)
                self.assertEqual(client.post(path+'/evaluate').status_code,202)
                submit.assert_called_with(self.t['id'],False,max_evaluations=None)

    def test_unknown_condition_and_missing_parts_require_review(self):
        with TestClient(app) as client:
            identity=repo.save_listing(self.t['id'],listing())
            for changes in ({'condition':'unknown'},{'matches_need':'unknown'}):
                with self.subTest(changes=changes):
                    a=analysis();a.update(changes)
                    item=repo.matches(self.t['id'])[0]
                    repo.save_evaluation(self.t['id'],identity,'evaluated',a,engine.key_for(self.t,item))
                    result=client.get(f"/api/topics/{self.t['id']}/listings").json()['listings'][0]
                    self.assertEqual(result['view'],'review')

    def test_api_complete_flow_and_error_states(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json()['app'],'BuyWatcher')
            response=client.post('/api/topics',json=topic());self.assertEqual(response.status_code,201)
            t=response.json()['topic'];tid=t['id']
            self.assertEqual(client.post('/api/topics',json={**topic(),'budget':-1}).status_code,422)
            with patch('app.services.ai.configured',return_value=True),patch('app.services.ai.card',return_value=analysis()):
                r=client.post(f'/api/topics/{tid}/listings',json=listing())
                self.assertEqual(r.status_code,201)
                app.state.worker.pool.submit(lambda:None).result(timeout=5)
                body=client.get(f'/api/topics/{tid}/listings').json()
                self.assertEqual(body['listings'][0]['view'],'relevant')
                iid=r.json()['listing_id']
                self.assertEqual(client.post(f'/api/topics/{tid}/listings/{iid}/feedback',json={'verdict':'like'}).status_code,200)
                self.assertEqual(client.get(f'/api/topics/{tid}/listings').json()['listings'][0]['verdict'],'like')
            self.assertEqual(client.post(f'/api/topics/{tid}/listings',json=listing(source='ebay')).status_code,422)
            self.assertEqual(client.get('/api/topics/9999/listings').status_code,404)
            self.assertEqual(client.get('/api/runs/9999').status_code,404)
            self.assertEqual(client.post('/api/topic-plan',json={'need':'test'}).status_code,503)
            index=Path(__file__).resolve().parents[1]/'app'/'static'/'index.html'
            if not index.exists():  # the frontend build is not committed: stand in for it
                index.write_text('<!doctype html><title>BuyWatcher</title>')
            self.assertEqual(client.get('/').status_code,200)
            self.assertIn('BuyWatcher',client.get('/').text)
            self.assertEqual(client.delete(f'/api/topics/{tid}').status_code,200)

    def test_stale_model_does_not_publish_old_analysis(self):
        with TestClient(app) as client:
            repo.save_listing(self.t['id'],listing())
            item=repo.matches(self.t['id'])[0]
            repo.save_evaluation(self.t['id'],item['id'],'evaluated',analysis(),'old-config')
            result=client.get(f"/api/topics/{self.t['id']}/listings").json()['listings'][0]
            self.assertEqual(result['state'],'pending');self.assertIsNone(result['analysis'])


class SizePolicyTest(unittest.TestCase):
    PROFILE={'shoe_size_eu':44,'clothing_sizes':['L','XL']}

    def assess(self,scope='fashion',profile=None,**card):
        return personalization.assess({'profile_scope':scope},card,profile or self.PROFILE)['status']

    def test_shoes_compare_eu_number_only(self):
        for size,expected in ((44,'pass'),(44.5,'unknown'),(43,'exclude'),(46,'exclude'),(None,'unknown')):
            with self.subTest(size=size):self.assertEqual(self.assess(category='footwear',shoe_size_eu=size),expected)

    def test_clothes_compare_letter_size(self):
        for size,expected in (('L','pass'),('XL','pass'),('XXL','unknown'),('M','unknown'),('S','exclude'),('3XL','exclude'),(None,'unknown')):
            with self.subTest(size=size):self.assertEqual(self.assess(category='clothing',clothing_size=size),expected)

    def test_kids_and_women_excluded(self):
        self.assertEqual(self.assess(category='clothing',clothing_size='L',gender='kids'),'exclude')
        self.assertEqual(self.assess(category='clothing',clothing_size='L',gender='women'),'exclude')
        self.assertEqual(self.assess(category='clothing',clothing_size='L',gender='unisex'),'pass')

    def test_profile_applies_only_to_its_scope_and_categories(self):
        self.assertEqual(self.assess(scope='none',category='footwear',shoe_size_eu=40),'none')
        self.assertEqual(self.assess(scope='footwear',category='clothing',clothing_size='S'),'none')
        self.assertEqual(self.assess(category='other'),'none')
        self.assertEqual(self.assess(profile={'shoe_size_eu':None,'clothing_sizes':['L']},category='footwear',shoe_size_eu=40),'none')

    def test_unknown_size_names_what_was_declared(self):
        result=personalization.assess({'profile_scope':'footwear'},{'category':'footwear','size':'UK 9','shoe_size_eu':None},self.PROFILE)
        self.assertIn('UK 9',result['reason'])


class EbayAccountDeletionTest(DatabaseFixture):
    def test_disabled_without_configuration(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/ebay/account-deletion',params={'challenge_code':'x'}).status_code,404)

    def test_challenge_and_seller_removal(self):
        import hashlib
        url='https://bw.example.com/ebay/account-deletion'
        with patch.dict(os.environ,{'EBAY_VERIFICATION_TOKEN':'t'*40,'EBAY_DELETION_ENDPOINT':url}),TestClient(app) as client:
            answer=client.get('/ebay/account-deletion',params={'challenge_code':'abc'}).json()
            self.assertEqual(answer,{'challengeResponse':hashlib.sha256(('abc'+'t'*40+url).encode()).hexdigest()})
            gone=repo.save_listing(self.t['id'],listing(1,source='ebay',seller='venditore1'))
            kept=repo.save_listing(self.t['id'],listing(2,source='ebay',seller='altro'))
            repo.save_evaluation(self.t['id'],gone,'evaluated',analysis(),'k')
            body={'metadata':{'topic':'MARKETPLACE_ACCOUNT_DELETION'},
                  'notification':{'notificationId':'n1','data':{'username':'venditore1','userId':'u1','eiasToken':'e'}}}
            self.assertEqual(client.post('/ebay/account-deletion',json=body).status_code,204)
            items={i['id']:i for i in repo.matches(self.t['id'])}
            self.assertEqual(items[gone]['seller'],'')
            self.assertEqual(items[gone]['state'],'pending')
            self.assertEqual(items[kept]['seller'],'altro')
            self.assertNotIn('venditore1',json.dumps(repo.history(gone)))


class ApiV1Test(DatabaseFixture):
    def test_openapi_snapshot_is_current(self):
        from app import export_openapi
        self.assertEqual(export_openapi.PATH.read_text(),export_openapi.render(),
                         'API cambiata: rigenera con uv run python -m app.export_openapi')

    def test_v1_routes_operation_ids_and_problem_details(self):
        with TestClient(app) as client:
            spec=client.get('/openapi.json').json()
            self.assertIn('/api/v1/topics',spec['paths'])
            self.assertFalse([p for p in spec['paths'] if p.startswith('/api/') and not p.startswith('/api/v1/')
                              and not p.startswith(('/api/channels','/api/feedback','/api/favorites','/api/deals'))])
            self.assertEqual(spec['paths']['/api/v1/topics']['post']['operationId'],'create_topic')
            response=client.get('/api/v1/topics/9999/listings')
            self.assertEqual(response.status_code,404)
            self.assertEqual(response.headers['content-type'],'application/problem+json')
            self.assertEqual(response.json()['code'],'topic_not_found')
            invalid=client.post('/api/v1/topics',json={'name':''})
            self.assertEqual((invalid.status_code,invalid.json()['code']),(422,'validation_error'))

    def test_if_match_on_topic_update(self):
        with TestClient(app) as client:
            current=self.t['revision']
            stale=client.put(f"/api/v1/topics/{self.t['id']}",json=topic(),headers={'If-Match':str(current+5)})
            self.assertEqual((stale.status_code,stale.json()['code']),(412,'version_mismatch'))
            ok=client.put(f"/api/v1/topics/{self.t['id']}",json=topic(),headers={'If-Match':f'"{current}"'})
            self.assertEqual(ok.json()['topic']['revision'],current+1)


if __name__=='__main__':unittest.main()


class NightScheduleTest(unittest.TestCase):
    def topic(self,last_run=None,interval=24):
        return {'active':True,'interval_hours':interval,'last_run':last_run}

    def at(self,text):
        return datetime.fromisoformat(text).astimezone(timezone.utc)

    def test_collects_once_per_night_and_never_by_day(self):
        night,day=self.at('2026-11-03T02:01:00+01:00'),self.at('2026-11-03T15:00:00+01:00')
        self.assertIsNone(engine.due(self.topic(),day))
        self.assertEqual(engine.due(self.topic(),night),'collect')
        yesterday={'state':'success','started_at':'2026-11-02T14:00:00+01:00','report':{}}
        self.assertEqual(engine.due(self.topic(yesterday),night),'collect')
        tonight={'state':'success','started_at':'2026-11-03T02:00:30+01:00','report':{'evaluation':{'pending':0,'evaluated':40}}}
        self.assertIsNone(engine.due(self.topic(tonight),night))
        self.assertIsNone(engine.due(self.topic({**tonight,'state':'running'}),night))

    def test_drains_queue_until_dawn_only_while_making_progress(self):
        night=self.at('2026-11-03T05:00:00+01:00')
        run={'state':'partial','started_at':'2026-11-03T02:00:30+01:00','report':{'evaluation':{'pending':30,'evaluated':12}}}
        self.assertEqual(engine.due(self.topic(run),night),'evaluate')
        stuck={**run,'report':{'evaluation':{'pending':30,'evaluated':0,'errors':5}}}
        self.assertIsNone(engine.due(self.topic(stuck),night))
        self.assertIsNone(engine.due(self.topic(run),self.at('2026-11-03T07:00:00+01:00')))

    def test_long_interval_skips_nights(self):
        night=self.at('2026-11-03T02:01:00+01:00')
        last={'state':'success','started_at':'2026-11-02T02:00:00+01:00','report':{}}
        self.assertIsNone(engine.due(self.topic(last,interval=48),night))
        self.assertEqual(engine.due(self.topic(last,interval=24),night),'collect')

    def test_vinted_publication_time_comes_from_the_main_photo(self):
        self.assertEqual(sources._photo_time({'high_resolution':{'timestamp':1762041600}}),'2025-11-02T00:00:00+00:00')
        self.assertEqual(sources._photo_time({'url':'x'}),'')
        self.assertEqual(sources._photo_time(None),'')
