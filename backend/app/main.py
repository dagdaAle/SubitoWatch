"""BuyWatcher API. A single application worker owns the scheduler and job queue."""
from __future__ import annotations

from pathlib import Path

import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from collections import Counter

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from app.services import ai
from app.services import engine
from app import legacy
from app.repositories import topics as repo
from app.services import scoring
from app import sources
from app.services import personalization
from app.schemas import ListingInput, TopicInput, BuyerProfile


@asynccontextmanager
async def lifespan(app):
    repo.init_db()
    app.state.worker=engine.Worker()
    app.state.worker.start()
    yield
    app.state.worker.close()


app=FastAPI(title='BuyWatcher',version='3.0.0',lifespan=lifespan)


def require_topic(topic_id):
    topic=repo.get_topic(topic_id)
    if not topic:
        raise HTTPException(404,'Topic non trovato')
    return topic


def require_idle(topic_id):
    require_topic(topic_id)
    previous=repo.runs(topic_id)
    if previous and previous[0]['state']=='running':
        raise HTTPException(409,'Attendi il completamento della ricerca in corso.')


@app.get('/health')
def health():
    with repo.connect() as db:
        db.execute('SELECT 1 FROM bw_topics').fetchone()
    return {'ok':True,'app':'BuyWatcher','ai_configured':ai.configured()}


@app.get('/api/config')
def config():
    return {'app':'BuyWatcher','ai_configured':ai.configured(),
            'vision_configured':bool(ai.configured() and os.getenv('BUYWATCHER_VISION_MODEL')),
            'sources':sources.catalog()}


@app.get('/api/topics')
def topics():
    topics=repo.list_topics()
    for topic in topics:
        topic['counts']=dict(Counter(item['state'] for item in current_items(topic)))
    return {'topics':topics}


def current_items(topic):
    items=repo.matches(topic['id'])
    personalized=engine.effective_topic(topic)
    for item in items:
        if item['state']=='evaluated' and item['evaluation_key']!=engine.key_for(topic,item):
            item.update(state='pending',analysis=None,error='Le preferenze, il topic o il modello sono cambiati: rivaluta l’annuncio.')
        if item['state']=='evaluated' and item.get('analysis'):
            item['analysis']=personalization.refine(personalized,item,item['analysis'])
    return items


@app.get('/api/topics/{topic_id}/marketplaces')
def marketplaces(topic_id:int):
    return {'marketplaces':sources.marketplace_searches(require_topic(topic_id))}


@app.get('/api/profile')
def profile():
    return {'profile':repo.get_profile()}


@app.put('/api/profile')
def update_profile(body:BuyerProfile):
    profile,affected=repo.save_profile(body.model_dump())
    return {'profile':profile,'affected_topic_ids':affected}


@app.post('/api/topics',status_code=201)
def create_topic(body:TopicInput):
    return {'topic':repo.save_topic(body.model_dump())}


@app.put('/api/topics/{topic_id}')
def update_topic(topic_id:int,body:TopicInput):
    require_idle(topic_id)
    return {'topic':repo.save_topic(body.model_dump(),topic_id)}


@app.delete('/api/topics/{topic_id}')
def delete_topic(topic_id:int):
    require_idle(topic_id)
    repo.delete_topic(topic_id)
    return {'ok':True}


class PlanInput(BaseModel):
    need:str=Field(min_length=3,max_length=4000)


@app.post('/api/topic-plan')
def plan_topic(body:PlanInput):
    try:
        proposal=ai.plan(body.need)
        allowed=set(TopicInput.model_fields)-{'sources','active','interval_hours','relevance_threshold'}
        proposal={k:v for k,v in proposal.items() if k in allowed}
        return {'topic':TopicInput.model_validate({**proposal,'need':body.need}).model_dump()}
    except (RuntimeError,ValidationError,TypeError,AttributeError):
        raise HTTPException(503,'Proposta non disponibile. Configura il modello o compila il topic manualmente.')


class RunOptions(BaseModel):
    max_evaluations:int|None=Field(default=None,ge=1,le=200)


@app.post('/api/topics/{topic_id}/refresh',status_code=202)
def refresh(topic_id:int,body:RunOptions|None=None):
    require_topic(topic_id)
    run_id=app.state.worker.submit(topic_id,max_evaluations=body.max_evaluations if body else None)
    if run_id is None:
        raise HTTPException(409,'Una ricerca per questo topic è già in corso.')
    return {'run_id':run_id}


@app.post('/api/topics/{topic_id}/evaluate',status_code=202)
def evaluate(topic_id:int,body:RunOptions|None=None):
    require_topic(topic_id)
    run_id=app.state.worker.submit(topic_id,False,max_evaluations=body.max_evaluations if body else None)
    if run_id is None:
        raise HTTPException(409,'Una valutazione per questo topic è già in corso.')
    return {'run_id':run_id}


@app.get('/api/topics/{topic_id}/runs')
def runs(topic_id:int):
    require_topic(topic_id)
    return {'runs':repo.runs(topic_id)}


@app.get('/api/runs/{run_id}')
def get_run(run_id:int):
    result=repo.get_run(run_id)
    if result is None:
        raise HTTPException(404,'Processo non trovato')
    return result


@app.post('/api/topics/{topic_id}/listings',status_code=201)
def import_listing(topic_id:int,body:ListingInput):
    require_idle(topic_id)
    # A caller cannot spoof official sources or bypass per-source access/AI policy.
    if body.source!='manual':
        raise HTTPException(422,'Gli annunci inseriti da te devono usare la fonte manual.')
    try:
        listing_id=repo.save_listing(topic_id,body.model_dump())
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    run_id=app.state.worker.submit(topic_id,False)
    return {'listing_id':listing_id,'run_id':run_id}


@app.get('/api/topics/{topic_id}/listings')
def listings(topic_id:int):
    topic=require_topic(topic_id)
    items=current_items(topic)
    # Never publish stale eBay display data beyond the documented six-hour window.
    items=[i for i in items if i['source']!='ebay' or (datetime.now(timezone.utc)-datetime.fromisoformat(i['last_seen'])).total_seconds()<6*3600]
    for item in items:
        item['recommendation']=scoring.recommendation(topic,item,items)
        analysis=item.get('analysis') or {}
        if item['state']!='evaluated':
            item['view']='review'
        elif analysis.get('requirement_failures') or analysis.get('relevance',0)<topic['relevance_threshold']:
            item['view']='excluded'
        elif analysis.get('requirement_unknowns') or analysis.get('missing_parts') or analysis.get('condition_grade','unknown')=='unknown' or analysis.get('risks') or analysis.get('confidence',0)<70 or item['availability']=='unavailable' or scoring.stale(item):
            item['view']='review'
        else:
            item['view']='relevant'
    # Topic matches retain independent evaluations; exact URLs are globally deduplicated.
    items.sort(key=lambda i:(i['recommendation']['score'] if i['recommendation']['score'] is not None else -1,
                            (i.get('analysis') or {}).get('relevance',-1)),reverse=True)
    return {'topic':topic,'listings':items}


@app.get('/api/listings/{listing_id}/history')
def history(listing_id:int):
    return {'history':repo.history(listing_id)}


class FeedbackInput(BaseModel):
    verdict:Literal['like','dislike']|None=None


@app.post('/api/topics/{topic_id}/listings/{listing_id}/feedback')
def feedback(topic_id:int,listing_id:int,body:FeedbackInput):
    require_topic(topic_id)
    try:
        repo.set_feedback(topic_id,listing_id,body.verdict)
    except ValueError:
        raise HTTPException(404,'Annuncio non trovato nel topic')
    return {'ok':True}


def ebay_deletion_config():
    token,endpoint=os.getenv('EBAY_VERIFICATION_TOKEN',''),os.getenv('EBAY_DELETION_ENDPOINT','')
    if not token or not endpoint:
        raise HTTPException(404,'Not Found')
    return token,endpoint


# Public path (Authentik bypass): eBay Marketplace Account Deletion notifications.
@app.get('/ebay/account-deletion')
def ebay_challenge(challenge_code:str):
    token,endpoint=ebay_deletion_config()
    # eBay requires SHA-256 of challengeCode + verificationToken + endpoint, exactly as registered.
    return {'challengeResponse':hashlib.sha256((challenge_code+token+endpoint).encode()).hexdigest()}


class EbayDeletionData(BaseModel):
    username:str=Field(default='',max_length=200)


class EbayDeletionNotification(BaseModel):
    data:EbayDeletionData


class EbayDeletionInput(BaseModel):
    notification:EbayDeletionNotification


@app.post('/ebay/account-deletion',status_code=204)
def ebay_account_deletion(body:EbayDeletionInput):
    ebay_deletion_config()
    # shortcut: X-EBAY-SIGNATURE is not verified, so anyone can blank a seller name (no other effect);
    # verify it with the Notification API public key once the keyset is active.
    if body.notification.data.username:
        repo.forget_ebay_seller(body.notification.data.username)


# Keep old MCP routes and storage contracts. No legacy scheduler is started.
# These routes remain isolated from the evaluated BuyWatcher feed.
for route in legacy.app.routes:
    if getattr(route,'path','').startswith(('/channels','/feedback','/favorites','/deals')):
        app.router.routes.append(route)

STATIC=Path(__file__).parent / 'static'
STATIC.mkdir(exist_ok=True)  # the frontend build is not committed; tests and dev run without it
app.mount('/',StaticFiles(directory=STATIC,html=True),name='static')
