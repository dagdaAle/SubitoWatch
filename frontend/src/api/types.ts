export interface TopicInput {
  name: string; need: string; keywords: string[]; requirements: string[]; preferences: string[];
  exclusions: string[]; accepted_defects: string; budget: number | null; location: string;
  shipping_allowed: boolean; sources: string[]; relevance_threshold: number; interval_hours: number; active: boolean;
  profile_scope: 'none' | 'footwear' | 'clothing' | 'fashion';
}
export interface BuyerProfile { shoe_size_eu: number | null; clothing_sizes: string[]; revision?: number }
export interface Run { id: number; state: string; started_at: string; finished_at: string | null;
  report: { sources?: Record<string, { state: string; found: number; errors: string[]; truncated?: boolean }>;
    evaluation?: { evaluated: number; cached: number; pending: number; errors: number }; error?: string } }
export interface Topic extends TopicInput { id: number; revision: number; counts: Record<string, number>; last_run: Run | null }
export interface Source { id: string; name: string; enabled: boolean; automatic: boolean; analysis: boolean; pricing: boolean; detail: string; policy_url?: string }
export interface Config { ai_configured: boolean; vision_configured: boolean; sources: Source[] }
export interface Card {
  name: string; brand: string | null; model: string | null; category: 'clothing' | 'footwear' | 'other';
  gender: string; size: string | null; size_source: 'platform' | 'title' | 'description' | 'photo' | null;
  clothing_size: string | null; shoe_size_eu: number | null; condition: string; defects: string[];
  ships_from: string | null; shipping: 'shipping' | 'pickup' | 'both' | 'unknown'; new_price: number | null;
  matches_need: 'yes' | 'no' | 'unknown'; matches_reason: string; deal: 'yes' | 'no' | 'unknown'; deal_reason: string;
  missing_info: string[]; images_examined: number; ai_model: string; version: string;
}
export interface Listing {
  id: number; listing_url: string; source: string; title: string; description: string;
  price: number | null; shipping_cost: number | null; fees: number | null; currency: string;
  town: string; images: string[]; condition: string; seller: string; is_shop: boolean;
  buying_format: string; availability: string; state: string; analysis: Card | null;
  attributes?: Record<string, string>; size_check: { status: string; reason: string } | null;
  view: string; published_at: string; first_seen: string; last_seen: string; evaluated_at: string | null;
  verdict: 'like' | 'dislike' | null; error: string | null;
  recommendation: { score: number | null; label: string; total_cost: number | null; reference: number | null;
    savings_percent: number | null; new_price: number | null; new_savings_percent: number | null;
    deal: 'yes' | 'no' | 'unknown'; deal_reason: string; reasons: string[];
    comparables: { id: number; url: string; total_cost: number }[] };
}

