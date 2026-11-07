"""Validated contracts shared by the API, connectors and AI evaluator."""
from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SOURCES = ('manual', 'subito', 'ebay', 'vinted', 'facebook', 'wallapop', 'astrosell')


def public_url(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname or ''
    if parts.scheme not in ('http', 'https') or not host or parts.username or parts.password:
        raise ValueError('È richiesto un URL pubblico http/https senza credenziali')
    if host in ('localhost', 'metadata.google.internal') or host.endswith(('.local', '.internal', '.localhost')) or '.' not in host:
        raise ValueError('URL locale non consentito')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Indirizzo privato non consentito')
    except ValueError as exc:
        if 'Indirizzo privato' in str(exc):
            raise
        # Not an IP literal. No server-side fetching of user-supplied URLs.
    if parts.port not in (None, 80, 443):
        raise ValueError('Porta URL non consentita')
    return value


class TopicInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=120)
    need: str = Field(min_length=3, max_length=4000)
    keywords: list[str] = Field(min_length=1, max_length=12)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    preferences: list[str] = Field(default_factory=list, max_length=20)
    exclusions: list[str] = Field(default_factory=list, max_length=30)
    accepted_defects: str = Field(default='', max_length=1000)
    budget: float | None = Field(default=None, gt=0)
    location: str = Field(default='', max_length=200)
    shipping_allowed: bool = True
    sources: list[Literal['manual', 'subito', 'ebay', 'vinted']] = Field(default_factory=lambda: ['manual'])
    relevance_threshold: int = Field(default=70, ge=0, le=100)
    interval_hours: int = Field(default=24, ge=6, le=168)
    active: bool = True
    profile_scope: Literal['none','footwear','clothing','fashion'] = 'none'

    @field_validator('name', 'need')
    @classmethod
    def strip_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Il campo non può essere vuoto')
        return value.strip()

    @field_validator('keywords', 'requirements', 'preferences', 'exclusions')
    @classmethod
    def clean_strings(cls, values: list[str]) -> list[str]:
        if any(len(v) > 300 for v in values):
            raise ValueError('Voce troppo lunga (massimo 300 caratteri)')
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))

    @model_validator(mode='after')
    def has_keywords(self):
        if not self.keywords:
            raise ValueError('Inserisci almeno una ricerca')
        self.sources = list(dict.fromkeys(self.sources))
        return self


class ListingInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    listing_url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default='', max_length=20000)
    price: float | None = Field(default=None, ge=0)
    shipping_cost: float | None = Field(default=None, ge=0)
    fees: float | None = Field(default=None, ge=0)
    currency: str = Field(default='EUR', pattern='^[A-Z]{3}$')
    town: str = Field(default='', max_length=200)
    images: list[str] = Field(default_factory=list, max_length=12)
    condition: str = Field(default='', max_length=500)
    seller: str = Field(default='', max_length=300)
    is_shop: bool = False
    buying_format: Literal['fixed', 'auction', 'unknown'] = 'fixed'
    source: Literal['manual', 'subito', 'ebay', 'vinted'] = 'manual'
    external_id: str = Field(default='', max_length=200)
    published_at: str = ''
    availability: Literal['active', 'unavailable', 'unknown'] = 'unknown'
    # Structured fields exactly as the source gives them (Subito features, Vinted size, eBay aspects).
    attributes: dict[str, str] = Field(default_factory=dict, max_length=60)

    @field_validator('listing_url')
    @classmethod
    def valid_url(cls, value: str) -> str:
        return public_url(value)

    @field_validator('attributes')
    @classmethod
    def short_attributes(cls, values: dict[str, str]) -> dict[str, str]:
        return {k.strip()[:100]: v.strip()[:500] for k, v in values.items() if k.strip() and v and v.strip()}

    @field_validator('images')
    @classmethod
    def valid_images(cls, values: list[str]) -> list[str]:
        return [public_url(v) for v in values]


CLOTHING_SIZES = ('XXS','XS','S','M','L','XL','XXL','3XL','4XL','5XL')


class Card(BaseModel):
    """What the model extracts from one listing: the facts shown on the card. Unknown stays None."""
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    category: Literal['clothing', 'footwear', 'other']
    gender: Literal['men', 'women', 'unisex', 'kids', 'unknown'] = 'unknown'
    size: str | None = Field(default=None, max_length=60)
    size_source: Literal['platform', 'title', 'description', 'photo'] | None = None
    clothing_size: Literal[CLOTHING_SIZES] | None = None
    shoe_size_eu: float | None = Field(default=None, ge=15, le=55)
    condition: Literal['new_with_tags', 'new', 'excellent', 'good', 'fair', 'poor', 'unknown']
    defects: list[str] = Field(default_factory=list, max_length=10)
    ships_from: str | None = Field(default=None, max_length=200)
    shipping: Literal['shipping', 'pickup', 'both', 'unknown'] = 'unknown'
    # The model's estimate of the new retail price: shown as an estimate, never as a verified price.
    new_price: float | None = Field(default=None, gt=0)
    matches_need: Literal['yes', 'no', 'unknown']
    matches_reason: str = Field(default='', max_length=600)
    deal: Literal['yes', 'no', 'unknown']
    deal_reason: str = Field(default='', max_length=600)
    missing_info: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('clothing_size', mode='before')
    @classmethod
    def upper_size(cls, value):
        value = value.strip().upper() if isinstance(value, str) else value
        return {'XXXL': '3XL', '': None}.get(value, value) if isinstance(value, str) else value


class BuyerProfile(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    shoe_size_eu: float | None = Field(default=None,ge=15,le=55)
    clothing_sizes: list[Literal[CLOTHING_SIZES]] = Field(default_factory=list,max_length=10)

    @field_validator('shoe_size_eu')
    @classmethod
    def half_size(cls,value):
        if value is not None and value*2 != int(value*2):
            raise ValueError('Usa una taglia EU intera o mezza taglia')
        return value

    @field_validator('clothing_sizes')
    @classmethod
    def unique_sizes(cls,values):
        return [size for size in CLOTHING_SIZES if size in values]
