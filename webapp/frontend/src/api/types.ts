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
export interface Analysis {
  relevance: number; confidence: number; product_key: string | null; configuration: string | null;
  condition_grade: string; requirement_failures: string[]; requirement_unknowns: string[];
  declared_condition: string[]; observations: { claim: string; basis: string; detail: string; image_index: number | null }[];
  missing_parts: string[]; unknowns: string[]; risks: string[]; questions: string[]; reason: string;
  images_examined: number; model: string; version: string;
  evaluation_stage?: 'size_filter' | 'text_filter' | 'full_analysis';
  size_check?: { status: string; reason: string };
}
export interface Listing {
  id: number; listing_url: string; source: string; title: string; description: string;
  price: number | null; shipping_cost: number | null; fees: number | null; currency: string;
  town: string; images: string[]; condition: string; seller: string; is_shop: boolean;
  buying_format: string; availability: string; state: string; analysis: Analysis | null;
  view: string; first_seen: string; last_seen: string; evaluated_at: string | null;
  verdict: 'like' | 'dislike' | null; error: string | null;
  recommendation: { score: number | null; label: string; total_cost: number | null; reference: number | null;
    savings_percent: number | null; reasons: string[]; comparables: { id: number; url: string; total_cost: number }[] };
}

export interface Marketplace { id:string; name:string; monitoring:boolean; status:'automatic'|'setup'|'external'; searches:{query:string;url:string}[] }
