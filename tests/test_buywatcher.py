"""Regression tests: migrations, evidence, AI gate, failure modes and price scoring."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
os.chdir(Path(__file__).resolve().parents[1]/'webapp')

from fastapi.testclient import TestClient
from pydantic import ValidationError
import ai
import engine
import repository as repo
import scoring
import scraper
import sources
import images as image_loader
import storage
from app import app
from models import Analysis,ListingInput,TopicInput


def topic(**kw):
    return TopicInput(name='Oggetto test',need='Un oggetto completo e funzionante',keywords=['oggetto test'],**kw).model_dump()


def listing(n=1,**kw):
    return ListingInput(listing_url=f'https://example.com/item/{n}',title='Oggetto modello test',price=100,
                        description='Oggetto in buone condizioni, completo',shipping_cost=0,fees=0,**kw).model_dump()


def analysis(**kw):
    return Analysis.model_validate(dict(relevance=95,confidence=90,product_key='marca modello test',configuration='kit completo',
        condition_grade='good',requirement_failures=[],requirement_unknowns=[],declared_condition=['Buone condizioni'],
        observations=[],missing_parts=[],unknowns=[],risks=[],questions=[],reason='Corrisponde al modello e alla configurazione richiesti',**kw)).model_dump()


class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'BUYWATCHER_DB':self.tmp.name+'/test.db','BUYWATCHER_AI_BASE_URL':'',
            'BUYWATCHER_AI_MODEL':'','BUYWATCHER_VISION_MODEL':'','BUYWATCHER_ENABLE_SUBITO':'',
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
        with patch('ai.configured',return_value=True),patch('ai.evaluate',return_value=analysis()) as evaluate:
            self.assertEqual(engine.evaluate_pending(self.t)['evaluated'],1)
            self.assertEqual(engine.evaluate_pending(self.t)['cached'],1)
            changed=listing();changed['description']='Descrizione modificata'
            repo.save_listing(self.t['id'],changed)
            engine.evaluate_pending(self.t)
            self.assertEqual(evaluate.call_count,2)

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
        with patch.dict(os.environ,{'BUYWATCHER_ENABLE_SUBITO':'true'}),patch('sources.search',side_effect=RuntimeError('outage')),patch('engine.time.sleep'):
            engine.run(t['id'],run_id)
        run=repo.get_run(run_id)
        self.assertEqual(run['state'],'partial')
        self.assertEqual(run['report']['sources']['subito']['state'],'failed')

    def test_partial_search_keeps_successful_data(self):
        t=repo.save_topic({**topic(sources=['subito']),'keywords':['good','bad']})
        run_id=repo.start_run(t['id'])
        raw={'listing_url':'https://www.subito.it/test.htm','title':'Oggetto','price':50}
        with patch.dict(os.environ,{'BUYWATCHER_ENABLE_SUBITO':'true'}),patch('sources.search',side_effect=[[raw],RuntimeError('outage')]),patch('engine.time.sleep'):
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
        self.item={**listing(), 'id':1,'state':'evaluated','analysis':analysis(),'last_seen':repo.now()}
        self.peers=[{**copy.deepcopy(self.item),'id':i,'listing_url':f'https://example.com/{i}','price':200} for i in (2,3,4)]

    def test_real_cost_and_reference(self):
        r=scoring.recommendation(self.topic,self.item,self.peers)
        self.assertEqual(r['reference'],200)
        self.assertEqual(r['savings_percent'],50)
        self.assertEqual(r['label'],'Potenziale affare')

    def test_missing_cost_no_score(self):
        self.item['fees']=None
        self.assertIsNone(scoring.recommendation(self.topic,self.item,self.peers)['score'])

    def test_irrelevant_never_bargain(self):
        self.item['analysis']['requirement_failures']=['Solo accessorio']
        r=scoring.recommendation(self.topic,self.item,self.peers)
        self.assertEqual(r['label'],'Non pertinente');self.assertIsNone(r['score'])

    def test_auction_and_unknown_condition_no_score(self):
        for change in ('auction','condition'):
            item=copy.deepcopy(self.item)
            if change=='auction':item['buying_format']='auction'
            else:item['analysis']['condition_grade']='unknown'
            self.assertIsNone(scoring.recommendation(self.topic,item,self.peers)['score'])

    def test_variants_not_comparable(self):
        self.peers[0]['analysis']['configuration']='solo corpo'
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

    def test_risk_caps_score(self):
        self.item['analysis']['risks']=['Verificare identità del modello']
        self.assertLess(scoring.recommendation(self.topic,self.item,self.peers)['score'],60)


class ExtractionTest(unittest.TestCase):
    def test_changed_html_is_error_not_empty_result(self):
        with self.assertRaises(RuntimeError):scraper._extract_ads('<html>challenge</html>')
        html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'initialState':{'items':{'originalList':[]}}}}})+'</script>'
        self.assertEqual(scraper._extract_ads(html),[])

    def test_failed_legacy_keywords_raise(self):
        with patch('scraper.search',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):scraper.search_keywords(['one','two'])

    def test_photo_evidence_requires_attached_images(self):
        a=analysis();a['observations']=[{'claim':'Danno','basis':'image','detail':'Foto 1','image_index':0}]
        with patch.dict(os.environ,{'BUYWATCHER_AI_MODEL':'test','BUYWATCHER_VISION_MODEL':''}),patch('ai.complete',return_value=a):
            with self.assertRaises(RuntimeError):ai.evaluate(topic(),listing())




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

    def test_vision_prepares_base64_and_remaps_photo_indexes(self):
        a=analysis();a['observations']=[{'claim':'Dettaglio','basis':'image','detail':'Foto allegata','image_index':0}]
        ad=listing();ad['images']=['https://example.com/missing.jpg','https://example.com/visible.jpg']
        with patch.dict(os.environ,{'BUYWATCHER_AI_MODEL':'test','BUYWATCHER_VISION_MODEL':'vision-test'}),patch('images.prepare',return_value=(['data:image/jpeg;base64,/9j/'],[1])),patch('ai.complete',return_value=a) as complete:
            result=ai.evaluate(topic(),ad)
        self.assertEqual(result['observations'][0]['image_index'],1)
        self.assertEqual(result['images_examined'],1)
        self.assertEqual(complete.call_args.kwargs['images'][0],'data:image/jpeg;base64,/9j/')

    def test_image_fetch_rejects_private_dns_resolution(self):
        import socket
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('images.socket.getaddrinfo',return_value=addresses),self.assertRaises(ValueError):
            image_loader.public_target('https://images.example.com/photo.jpg')

    def test_image_connection_pins_the_resolved_address(self):
        import socket
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        with patch('images.socket.getaddrinfo',return_value=addresses):
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
            'estimatedAvailabilities':[]}
        with patch.object(sources.EBAY,'get',return_value=raw):
            result=sources.EBAY.detail({'itemId':raw['itemId']})
        self.assertEqual(result['description'],'Completo')
        self.assertEqual(result['buying_format'],'auction')
        self.assertEqual(result['shipping_cost'],10)
        self.assertEqual(len(result['images']),2)
        self.assertIsNone(result['fees'])

    def test_validation_and_private_urls(self):
        for url in ('http://127.0.0.1/test','file:///tmp/x','http://host.local/x','http://[::1]/x','https://user:pass@example.com/a'):
            with self.subTest(url=url),self.assertRaises(ValidationError):ListingInput(listing_url=url,title='test')
        with self.assertRaises(ValidationError):TopicInput(name=' ',need='test',keywords=['x'])
        with self.assertRaises(ValidationError):TopicInput(name='test',need='test',keywords=[' '])


class ApiTest(DatabaseFixture):
    def test_api_complete_flow_and_error_states(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json()['app'],'BuyWatcher')
            response=client.post('/api/topics',json=topic());self.assertEqual(response.status_code,201)
            t=response.json()['topic'];tid=t['id']
            self.assertEqual(client.post('/api/topics',json={**topic(),'budget':-1}).status_code,422)
            with patch('ai.configured',return_value=True),patch('ai.evaluate',return_value=analysis()):
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


if __name__=='__main__':unittest.main()
