"""BuyWatcher API. A single application worker owns the scheduler and job queue."""
from __future__ import annotations

from pathlib import Path

import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from collections import Counter

from fastapi import APIRouter, FastAPI, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from app.services import ai
from app.services import engine
from app import legacy
from app.repositories import topics as repo
from app.services import scoring
from app import sources
from app.services import personalization
from app import errors
from app.errors import ApiError
from app.schemas import ListingInput, TopicInput, BuyerProfile


@asynccontextmanager
async def lifespan(app):
    repo.init_db()
    app.state.worker=engine.Worker()
    app.state.worker.start()
    yield
    app.state.worker.close()


app=FastAPI(title='BuyWatcher',version='3.1.0',lifespan=lifespan,
            # operation_id = function name: stable names for generated clients and MCP parity.
            generate_unique_id_function=lambda route:route.name)
errors.install(app)
router=APIRouter()


def require_topic(topic_id):
    topic=repo.get_topic(topic_id)
    if not topic:
        raise ApiError(404,'topic_not_found','Topic non trovato')
    return topic


def check_version(if_match,revision):
    # shortcut: If-Match is optional until every client sends it; then answer 428 when missing.
    if if_match is not None and if_match.strip('"')!=str(revision):
        raise ApiError(412,'version_mismatch',f'Versione cambiata: attuale {revision}. Ricarica e riprova.')


def require_idle(topic_id):
    require_topic(topic_id)
    previous=repo.runs(topic_id)
    if previous and previous[0]['state']=='running':
        raise ApiError(409,'run_in_progress','Attendi il completamento della ricerca in corso.')


@app.get('/health')
def health():
    with repo.connect() as db:
        db.execute('SELECT 1 FROM bw_topics').fetchone()
    return {'ok':True,'app':'BuyWatcher','ai_configured':ai.configured()}


@router.get('/config')
def config():
    return {'app':'BuyWatcher','ai_configured':ai.configured(),
            'vision_configured':bool(ai.configured() and os.getenv('BUYWATCHER_VISION_MODEL')),
            'sources':sources.catalog()}


@router.get('/topics')
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


@router.get('/topics/{topic_id}/marketplaces')
def marketplaces(topic_id:int):
    return {'marketplaces':sources.marketplace_searches(require_topic(topic_id))}


@router.get('/profile')
def profile():
    return {'profile':repo.get_profile()}


@router.put('/profile')
def update_profile(body:BuyerProfile,if_match:str|None=Header(default=None)):
    check_version(if_match,repo.get_profile()['revision'])
    profile,affected=repo.save_profile(body.model_dump())
    return {'profile':profile,'affected_topic_ids':affected}


@router.post('/topics',status_code=201)
def create_topic(body:TopicInput):
    return {'topic':repo.save_topic(body.model_dump())}


@router.put('/topics/{topic_id}')
def update_topic(topic_id:int,body:TopicInput,if_match:str|None=Header(default=None)):
    require_idle(topic_id)
    check_version(if_match,require_topic(topic_id)['revision'])
    return {'topic':repo.save_topic(body.model_dump(),topic_id)}


@router.delete('/topics/{topic_id}')
def delete_topic(topic_id:int):
    require_idle(topic_id)
    repo.delete_topic(topic_id)
    return {'ok':True}


class PlanInput(BaseModel):
    need:str=Field(min_length=3,max_length=4000)


@router.post('/topic-plan')
def plan_topic(body:PlanInput):
    try:
        proposal=ai.plan(body.need)
        allowed=set(TopicInput.model_fields)-{'sources','active','interval_hours','relevance_threshold'}
        proposal={k:v for k,v in proposal.items() if k in allowed}
        return {'topic':TopicInput.model_validate({**proposal,'need':body.need}).model_dump()}
    except (RuntimeError,ValidationError,TypeError,AttributeError):
        raise ApiError(503,'ai_unavailable','Proposta non disponibile. Configura il modello o compila il topic manualmente.')


class RunOptions(BaseModel):
    max_evaluations:int|None=Field(default=None,ge=1,le=200)


@router.post('/topics/{topic_id}/refresh',status_code=202)
def refresh(topic_id:int,body:RunOptions|None=None):
    require_topic(topic_id)
    run_id=app.state.worker.submit(topic_id,max_evaluations=body.max_evaluations if body else None)
    if run_id is None:
        raise ApiError(409,'run_in_progress','Una ricerca per questo topic è già in corso.')
    return {'run_id':run_id}


@router.post('/topics/{topic_id}/evaluate',status_code=202)
def evaluate(topic_id:int,body:RunOptions|None=None):
    require_topic(topic_id)
    run_id=app.state.worker.submit(topic_id,False,max_evaluations=body.max_evaluations if body else None)
    if run_id is None:
        raise ApiError(409,'run_in_progress','Una valutazione per questo topic è già in corso.')
    return {'run_id':run_id}


@router.get('/topics/{topic_id}/runs')
def runs(topic_id:int):
    require_topic(topic_id)
    return {'runs':repo.runs(topic_id)}


@router.get('/runs/{run_id}')
def get_run(run_id:int):
    result=repo.get_run(run_id)
    if result is None:
        raise ApiError(404,'run_not_found','Processo non trovato')
    return result


@router.post('/topics/{topic_id}/listings',status_code=201)
def import_listing(topic_id:int,body:ListingInput):
    require_idle(topic_id)
    # A caller cannot spoof official sources or bypass per-source access/AI policy.
    if body.source!='manual':
        raise ApiError(422,'source_not_manual','Gli annunci inseriti da te devono usare la fonte manual.')
    try:
        listing_id=repo.save_listing(topic_id,body.model_dump())
    except ValueError as exc:
        raise ApiError(409,'listing_source_conflict',str(exc)) from exc
    run_id=app.state.worker.submit(topic_id,False)
    return {'listing_id':listing_id,'run_id':run_id}


@router.get('/topics/{topic_id}/listings')
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


@router.get('/listings/{listing_id}/history')
def history(listing_id:int):
    return {'history':repo.history(listing_id)}


class FeedbackInput(BaseModel):
    verdict:Literal['like','dislike']|None=None


@router.post('/topics/{topic_id}/listings/{listing_id}/feedback')
def feedback(topic_id:int,listing_id:int,body:FeedbackInput):
    require_topic(topic_id)
    try:
        repo.set_feedback(topic_id,listing_id,body.verdict)
    except ValueError:
        raise ApiError(404,'listing_not_in_topic','Annuncio non trovato nel topic')
    return {'ok':True}


def ebay_deletion_config():
    token,endpoint=os.getenv('EBAY_VERIFICATION_TOKEN',''),os.getenv('EBAY_DELETION_ENDPOINT','')
    if not token or not endpoint:
        raise ApiError(404,'not_found','Not Found')
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


app.include_router(router,prefix='/api/v1')
# shortcut: unversioned alias for today's frontend; remove when the new frontend (plan 04) ships.
app.include_router(router,prefix='/api',include_in_schema=False)


# Keep old MCP routes and storage contracts. No legacy scheduler is started.
# These routes remain isolated from the evaluated BuyWatcher feed.
for route in legacy.app.routes:
    if getattr(route,'path','').startswith(('/channels','/feedback','/favorites','/deals')):
        app.router.routes.append(route)

STATIC=Path(__file__).parent / 'static'
STATIC.mkdir(exist_ok=True)  # the frontend build is not committed; tests and dev run without it
app.mount('/',StaticFiles(directory=STATIC,html=True),name='static')
