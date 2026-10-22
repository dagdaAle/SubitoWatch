"""Bounded background jobs, explicit partial failures and cached AI evaluations."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import ai
import repository as repo
import sources
import personalization
from models import ListingInput

log=logging.getLogger('buywatcher')


def publication_time(item):
    for value in (item.get('published_at'), item.get('first_seen')):
        try:
            date = datetime.fromisoformat(value)
            return date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            continue
    return 0


def effective_topic(topic):
    return {**topic,'buyer_profile':personalization.preferences(topic,repo.get_profile())} if topic.get('profile_scope','none')!='none' else topic


def key_for(topic,item):
    topic=effective_topic(topic)
    return item['content_hash']+':'+repo.digest({'topic':topic,'model':ai.signature(),
        'analysis_allowed':sources.source_config(item['source'])['analysis']})


def evaluate_pending(topic,max_evaluations=None):
    report={'evaluated':0,'cached':0,'pending':0,'errors':0}
    limit=max(1,min(200,int(os.getenv('BUYWATCHER_MAX_AI_PER_RUN','40'))))
    if max_evaluations is not None:
        limit=min(limit,max(1,max_evaluations))
    for item in sorted(repo.matches(topic['id']), key=publication_time, reverse=True):
        key=key_for(topic,item)
        if item['state']=='evaluated' and item['evaluation_key']==key:
            report['cached']+=1
            continue
        if not ai.configured() or not sources.source_config(item['source'])['analysis']:
            repo.save_evaluation(topic['id'],item['id'],'pending',error='AI non configurata o analisi non autorizzata per la fonte.')
            report['pending']+=1
            continue
        if report['evaluated']+report['errors']>=limit:
            report['pending']+=1
            continue
        repo.save_evaluation(topic['id'],item['id'],'evaluating')
        try:
            analysis=ai.evaluate(effective_topic(topic),item)
            if key!=key_for(repo.get_topic(topic['id']),item):
                repo.save_evaluation(topic['id'],item['id'],'pending')
                report['pending']+=1
                continue
            saved=repo.save_evaluation(topic['id'],item['id'],'evaluated',analysis,key)
            report['evaluated' if saved else 'pending']+=1
        except Exception:
            # No untrusted AI/provider response or credentials in public error messages.
            repo.save_evaluation(topic['id'],item['id'],'error',error='Valutazione non completata. Verifica il modello e riprova.')
            log.warning('AI evaluation failed for topic=%s listing=%s',topic['id'],item['id'])
            report['errors']+=1
    return report


def run(topic_id,run_id,collect=True,max_evaluations=None):
    report={'sources':{},'evaluation':{}}
    try:
        topic=repo.get_topic(topic_id)
        if not topic:
            return
        if collect:
            for source in topic['sources']:
                if source=='manual':
                    continue
                config=sources.source_config(source)
                if not config['enabled']:
                    report['sources'][source]={'state':'disabled','found':0,'errors':['Fonte non configurata o accesso non abilitato.']}
                    continue
                source_report={'state':'success','found':0,'errors':[]}
                seen=set()
                detail_limit=max(1,min(200,int(os.getenv('BUYWATCHER_MAX_DETAILS_PER_SOURCE','30'))))
                for keyword in topic['keywords']:
                    try:
                        raw_items=sources.search(source,keyword,topic)
                    except Exception:
                        source_report['errors'].append('Ricerca non riuscita: '+keyword)
                        log.warning('Source search failed: source=%s topic=%s',source,topic_id)
                        time.sleep(1)
                        continue
                    for raw in raw_items:
                        identity=raw.get('itemId') or raw.get('listing_url')
                        if identity in seen:
                            continue
                        seen.add(identity)
                        if source_report['found']>=detail_limit:
                            source_report['truncated']=True
                            break
                        try:
                            listing=ListingInput.model_validate(sources.enrich(source,raw)).model_dump()
                            repo.save_listing(topic_id,listing)
                            source_report['found']+=1
                        except Exception:
                            source_report['errors'].append('Dettagli di un annuncio non recuperabili.')
                        if source=='ebay':
                            time.sleep(0.2)
                    # One second between keyword searches, no rate increase to legacy scraper.
                    time.sleep(1)
                if source_report['errors']:
                    source_report['state']='partial' if source_report['found'] else 'failed'
                report['sources'][source]=source_report
        report['evaluation']=evaluate_pending(topic,max_evaluations)
        bad=any(v['state'] in ('failed','partial','disabled') for v in report['sources'].values())
        evaluation=report['evaluation']
        state='partial' if bad or evaluation['errors'] or evaluation['pending'] else 'success'
        repo.finish_run(run_id,state,report)
    except Exception:
        log.exception('BuyWatcher run failed: topic=%s',topic_id)
        repo.finish_run(run_id,'failed',{'error':'Processo interrotto. Controlla i log applicativi.'})


class Worker:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='buywatcher')
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.scheduler,daemon=True)

    def submit(self,topic_id,collect=True,max_evaluations=None):
        run_id=repo.start_run(topic_id)
        if run_id is not None:
            self.pool.submit(run,topic_id,run_id,collect,max_evaluations)
        return run_id

    def scheduler(self):
        # First auto collection after a minute; topic edits/imports never trigger hidden searches.
        while not self.stop.wait(60):
            for topic in repo.list_topics():
                if not topic['active']:
                    continue
                previous=topic['last_run']
                if previous and previous['state']=='running':
                    continue
                stamp=previous['started_at'] if previous else topic['updated_at']
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()
                if age>=topic['interval_hours']*3600:
                    self.submit(topic['id'])

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.pool.shutdown(wait=True)
