import { useCallback, useEffect, useRef, useState } from 'react';
import { request } from './api/client';
import type { Config, Topic, TopicInput, Listing, Run } from './api/types';

const emptyTopic: TopicInput = { name: '', need: '', keywords: [], requirements: [], preferences: [], exclusions: [], accepted_defects: '',
  budget: null, location: '', shipping_allowed: true, sources: ['manual'], relevance_threshold: 70, interval_hours: 24, active: true };
const money = (n: number | null, currency = 'EUR') => n === null ? 'Non noto' : new Intl.NumberFormat('it-IT', { style: 'currency', currency }).format(n);
const when = (s: string | null) => s ? new Date(s).toLocaleString('it-IT') : 'Mai';
const stateLabel: Record<string, string> = { success: 'Completata', partial: 'Parziale · richiede attenzione', failed: 'Non riuscita', running: 'In corso', interrupted: 'Interrotta', disabled: 'Non configurata' };

export default function App() {
  const [config, setConfig] = useState<Config>();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [items, setItems] = useState<Listing[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [view, setView] = useState('relevant');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [topicForm, setTopicForm] = useState<TopicInput | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [showSources, setShowSources] = useState(false);
  const activeRef = useRef(activeId); activeRef.current = activeId;
  const active = topics.find(t => t.id === activeId);
  const running = active?.last_run?.state === 'running';

  const load = useCallback(async (id: number | null) => {
    const [c, t] = await Promise.all([request<Config>('/api/config'), request<{ topics: Topic[] }>('/api/topics')]);
    setConfig(c); setTopics(t.topics);
    if (id !== null) {
      const [l, r] = await Promise.all([request<{ listings: Listing[] }>(`/api/topics/${id}/listings`), request<{ runs: Run[] }>(`/api/topics/${id}/runs`)]);
      if (activeRef.current === id) { setItems(l.listings); setRuns(r.runs); }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(''); setItems([]); setRuns([]);
    load(activeId).catch(e => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [activeId, load]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => { load(activeId).catch(e => setError(e.message)); }, 3000);
    return () => window.clearInterval(timer);
  }, [running, activeId, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await fn(); await load(activeId); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const feedback = (l: Listing, verdict: 'like' | 'dislike') => act(() => request(`/api/topics/${activeId}/listings/${l.id}/feedback`, 'POST', { verdict: l.verdict === verdict ? null : verdict }));
  const visible = items.filter(l => {
    if (search && !`${l.title} ${l.description}`.toLowerCase().includes(search.toLowerCase())) return false;
    if (view === 'favorites') return l.verdict === 'like';
    if (view === 'dismissed') return l.verdict === 'dislike';
    if (l.verdict === 'dislike') return false;
    if (view === 'all') return l.state === 'evaluated' && l.view !== 'excluded';
    return l.view === view;
  });

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="BuyWatcher home"><span className="brand-mark">◎</span> BuyWatcher</a>
      <p className="muted tagline">Trova ciò che ti serve.<br />Capisci se ne vale la pena.</p>
      <button className="primary wide" onClick={() => { setEditing(null); setTopicForm({ ...emptyTopic }); }}>＋ Nuovo topic</button>
      <div className="nav-label">I TUOI TOPIC <span>{topics.length}</span></div>
      <nav>{topics.map(t => <button key={t.id} className={`topic-link ${activeId === t.id ? 'active' : ''}`} onClick={() => { setActiveId(t.id); setView('relevant'); }}>
        <span>◉</span><span className="topic-name">{t.name}<small>{t.last_run?.state === 'running' ? 'Ricerca in corso…' : `${t.counts.evaluated ?? 0} valutati · ${t.counts.pending ?? 0} in attesa`}</small></span>
      </button>)}</nav>
      <div className="sidebar-bottom"><button className="ghost wide" onClick={() => setShowSources(true)}>◇ Fonti e configurazione</button><span className={`status-dot ${config?.ai_configured ? 'green' : ''}`} /> AI {config?.ai_configured ? 'configurata' : 'da configurare'}</div>
    </aside>
    <main>
      <header className="topbar"><span className="eyebrow">IL TUO RADAR DELL’USATO</span><div className="actions"><button className="ghost sources-mobile" onClick={() => setShowSources(true)}>Fonti</button><button className="ghost" disabled={loading} onClick={() => act(() => load(activeId))}>↻ Ricarica</button></div></header>
      {error && <div className="notice error" role="alert">{error} <button onClick={() => setError('')}>Chiudi</button></div>}
      {config && !config.ai_configured && <div className="notice">L’AI non è configurata. Puoi preparare i topic e inserire annunci: resteranno “Da verificare”, senza punteggi inventati. <button onClick={() => setShowSources(true)}>Configurazione</button></div>}
      {loading ? <div className="empty">Caricamento del radar…</div> : !active ? <section className="welcome"><span className="eyebrow">DAL BISOGNO ALL’ACQUISTO</span><h1>Cosa stai cercando?</h1><p>Descrivi il tuo prossimo acquisto. BuyWatcher raccoglie i candidati e valuta pertinenza, condizioni e convenienza prima di consigliarteli.</p><button className="primary" onClick={() => { setEditing(null); setTopicForm({ ...emptyTopic }); }}>Crea il primo topic →</button><div className="welcome-grid"><div><b>01 / Il bisogno</b><p>Uso, budget, requisiti e difetti che accetti.</p></div><div><b>02 / Le evidenze</b><p>Descrizioni, foto disponibili e informazioni mancanti.</p></div><div><b>03 / Il confronto</b><p>Costo totale e offerte equivalenti, quando verificabili.</p></div></div></section> : <>
        <section className="topic-heading"><div><span className="eyebrow">TOPIC DI ACQUISTO {active.active ? '' : '· AUTOMAZIONE IN PAUSA'}</span><h1>{active.name}</h1><p>{active.need}</p><div className="chips"><span>{active.budget ? `Budget ${money(active.budget)}` : 'Budget libero'}</span><span>{active.location || 'Località non specificata'}</span><span>{active.shipping_allowed ? 'Spedizione ammessa' : 'Ritiro'}</span><span>Ogni {active.interval_hours} ore</span></div></div><div className="actions"><button className="ghost" disabled={running} onClick={() => { setEditing(active.id); setTopicForm(active); }}>Modifica</button><button className="primary" disabled={busy || running} onClick={() => act(() => request(`/api/topics/${active.id}/refresh`, 'POST'))}>{running ? '◌ In elaborazione…' : 'Avvia ricerca →'}</button></div></section>
        <div className="metrics"><div><strong>{items.filter(i => i.view === 'relevant').length}</strong><span>Pertinenti valutati</span></div><div><strong>{items.filter(i => i.view === 'review').length}</strong><span>Da verificare</span></div><div><strong>{items.filter(i => (i.recommendation.score ?? 0) >= 75).length}</strong><span>Potenziali affari</span></div><div><strong className="small">{active.last_run ? stateLabel[active.last_run.state] : 'Non ancora eseguita'}</strong><span>Ultima esecuzione</span></div></div>
        <details className="run-panel"><summary>Stato delle fonti e delle esecuzioni <span>{running ? 'In corso' : when(active.last_run?.finished_at ?? null)}</span></summary>{runs.length === 0 ? <p>Nessuna ricerca eseguita.</p> : runs.slice(0, 5).map(r => <div className="run" key={r.id}><b>{stateLabel[r.state]} · {when(r.started_at)}</b>{r.report.error && <p>{r.report.error}</p>}{Object.entries(r.report.sources ?? {}).map(([name, s]) => <p key={name}>{name}: {stateLabel[s.state] ?? s.state} · {s.found} raccolti {s.truncated && '· limite raggiunto'}{s.errors.length > 0 && <small>{s.errors.join(' · ')}</small>}</p>)}{r.report.evaluation && <p>AI: {r.report.evaluation.evaluated} valutati · {r.report.evaluation.cached} già valutati · {r.report.evaluation.pending} in attesa · {r.report.evaluation.errors} errori</p>}</div>)}</details>
        <div className="result-tools"><div className="tabs">{[['relevant','Consigliati'],['review','Da verificare'],['all','Tutti i pertinenti'],['excluded','Esclusi'],['favorites','Salvati'],['dismissed','Scartati']].map(([id,label]) => <button key={id} className={view === id ? 'chosen' : ''} onClick={() => setView(id)}>{label}</button>)}</div><div className="actions"><button className="ghost" disabled={running || busy || !config?.ai_configured} onClick={() => act(() => request(`/api/topics/${active.id}/evaluate`, 'POST'))}>Valuta in attesa</button><button className="secondary" disabled={running} onClick={() => setImporting(true)}>＋ Inserisci annuncio</button></div></div>
        <input className="search" placeholder="Filtra per titolo o descrizione…" aria-label="Filtra risultati" value={search} onChange={e => setSearch(e.target.value)} />
        {visible.length === 0 ? <div className="empty"><span>◎</span><h2>Nessun risultato in questa vista</h2><p>Avvia una ricerca o inserisci un annuncio. I candidati non valutati sono nella vista “Da verificare”.</p></div> : <>
          {['other','ebay'].map(group => { const groupItems = visible.filter(i => group === 'ebay' ? i.source === 'ebay' : i.source !== 'ebay'); return groupItems.length > 0 && <section key={group} className="results-section"><h2>{group === 'ebay' ? 'Offerte eBay · sezione dedicata' : 'Il tuo radar'} <span>{groupItems.length}</span></h2><div className="listing-grid">{groupItems.map(l => <article className="listing-card" key={l.id}><button className="image-button" onClick={() => setSelected(l)}>{l.images[0] ? <img src={l.images[0]} alt={l.title} loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none'; }} /> : <span className="image-placeholder">◇</span>}<span className="source-badge">{l.source === 'manual' ? 'Inserito da te' : l.source}</span></button><div className="card-body"><div className="price-line"><strong>{money(l.recommendation.total_cost ?? l.price, l.currency)}</strong><small>{l.recommendation.total_cost === null ? 'costi incompleti' : 'totale'}</small></div><button className="title-button" onClick={() => setSelected(l)}>{l.title}</button><p className="card-location">{l.town || 'Località non specificata'} · {l.buying_format === 'auction' ? 'Asta' : l.is_shop ? 'Negozio' : 'Venditore'}</p><div className="score-row"><span>Pertinenza <b>{l.analysis ? `${l.analysis.relevance}/100` : '—'}</b></span><span>Convenienza <b>{l.recommendation.score === null ? '—' : `${l.recommendation.score}/100`}</b></span></div><p className={`deal-label ${(l.recommendation.score ?? 0) >= 75 ? 'good' : ''}`}>{l.recommendation.label}</p><p className="card-reason">{l.analysis?.reason || l.error || 'In attesa della valutazione AI.'}</p><div className="card-footer"><small>{l.analysis ? `Confidenza ${l.analysis.confidence}/100 · ${l.analysis.images_examined} foto esaminate` : 'Nessuna valutazione disponibile'}</small><div><button aria-label="Salva annuncio" aria-pressed={l.verdict === 'like'} className={l.verdict === 'like' ? 'saved' : ''} disabled={busy} onClick={() => feedback(l,'like')}>♡</button><button aria-label="Scarta annuncio" aria-pressed={l.verdict === 'dislike'} disabled={busy} onClick={() => feedback(l,'dislike')}>×</button></div></div></div></article>)}</div></section>; })}
        </>}
      </>}
    </main>
    {topicForm && config && <TopicForm initial={topicForm} editing={editing !== null} config={config} onClose={() => setTopicForm(null)} onSave={async body => {
      const result = await request<{ topic: Topic }>(editing === null ? '/api/topics' : `/api/topics/${editing}`, editing === null ? 'POST' : 'PUT', body);
      setTopicForm(null); setActiveId(result.topic.id); await load(activeId);
    }} onDelete={editing === null ? undefined : async () => { await request(`/api/topics/${editing}`, 'DELETE'); setTopicForm(null); setActiveId(null); await load(null); }} />}
    {importing && activeId !== null && <ImportForm onClose={() => setImporting(false)} onSave={async body => { await request(`/api/topics/${activeId}/listings`, 'POST', body); setImporting(false); await load(activeId); setView('review'); }} />}
    {selected && <Detail listing={selected} onClose={() => setSelected(null)} />}
    {showSources && config && <Modal title="Fonti e configurazione" onClose={() => setShowSources(false)}><p className="muted">Testo AI: {config.ai_configured ? 'configurato' : 'da configurare'} · Analisi foto: {config.vision_configured ? 'configurata' : 'da configurare'}. Le credenziali restano sul server.</p>{config.sources.map(s => <div className="source-row" key={s.id}><b>{s.name}</b><span className={`pill ${s.enabled ? 'good' : ''}`}>{s.enabled ? 'Disponibile' : 'Non attiva'}</span><p>{s.detail}</p>{s.policy_url && <a href={s.policy_url} target="_blank" rel="noreferrer">Condizioni della fonte ↗</a>}</div>)}<p className="muted">Configurazione e limiti dei connettori sono descritti nel SETUP.md del progetto. Nessun punteggio economico è garantito senza dati sufficienti.</p></Modal>}
  </div>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const el = dialog.current; el?.showModal(); return () => el?.close(); }, []);
  return <dialog ref={dialog} className="modal" onCancel={onClose} onClick={e => { if (e.target === dialog.current) onClose(); }}><header><h2>{title}</h2><button className="ghost" aria-label="Chiudi" onClick={onClose}>×</button></header>{children}</dialog>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
const split = (s: string) => s.split('\n').map(x => x.trim()).filter(Boolean);

function TopicForm({ initial, editing, config, onClose, onSave, onDelete }: { initial: TopicInput; editing: boolean; config: Config; onClose: () => void; onSave: (t: TopicInput) => Promise<void>; onDelete?: () => Promise<void> }) {
  const [form, setForm] = useState(initial); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const set = <K extends keyof TopicInput>(key: K, value: TopicInput[K]) => setForm(f => ({ ...f, [key]: value }));
  const execute = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <Modal title={editing ? 'Modifica il topic' : 'Cosa vuoi comprare?'} onClose={onClose}><form onSubmit={e => { e.preventDefault(); execute(() => onSave(form)); }}>
    <Field label="Descrivi il bisogno e l’uso previsto"><textarea required minLength={3} maxLength={4000} rows={3} placeholder="Che oggetto cerchi, per farci cosa e con quali vincoli?" value={form.need} onChange={e => set('need',e.target.value)} /></Field>
    <button type="button" className="secondary" disabled={busy || !config.ai_configured || form.need.trim().length < 3} onClick={() => execute(async () => { const r = await request<{ topic: TopicInput }>('/api/topic-plan','POST',{ need:form.need }); setForm({ ...form,...r.topic, sources:form.sources }); })}>✦ Prepara la ricerca con l’AI</button><p className="muted help">Controlla la proposta prima di salvarla. Puoi compilare tutto manualmente.</p>
    <Field label="Nome del topic"><input required maxLength={120} value={form.name} onChange={e => set('name',e.target.value)} /></Field>
    <Field label="Ricerche · una per riga"><textarea required rows={3} value={form.keywords.join('\n')} onChange={e => set('keywords',e.target.value.split('\n'))} /></Field>
    <div className="form-grid"><Field label="Budget totale €"><input type="number" min="0.01" step="0.01" value={form.budget ?? ''} onChange={e => set('budget',e.target.value ? Number(e.target.value) : null)} /></Field><Field label="Località"><input maxLength={200} placeholder="Comune; Subito cerca nella provincia di Verona" value={form.location} onChange={e => set('location',e.target.value)} /></Field></div>
    {(['requirements','preferences','exclusions'] as const).map((key,i) => <Field key={key} label={['Requisiti obbligatori · uno per riga','Preferenze · una per riga','Da escludere · una voce per riga'][i]}><textarea rows={2} value={form[key].join('\n')} onChange={e => set(key,e.target.value.split('\n'))} /></Field>)}
    <Field label="Difetti che accetti"><input maxLength={1000} value={form.accepted_defects} onChange={e => set('accepted_defects',e.target.value)} /></Field>
    <fieldset><legend>Fonti da interrogare</legend>{config.sources.filter(s => ['manual','subito','ebay'].includes(s.id)).map(s => <label className="check" key={s.id}><input type="checkbox" checked={form.sources.includes(s.id)} disabled={!s.enabled} onChange={e => set('sources', e.target.checked ? [...form.sources,s.id] : form.sources.filter(x => x !== s.id))} />{s.name}{!s.enabled && ' · da configurare'}</label>)}<p className="muted help">Vinted, Wallapop e Astrosell non hanno ancora un connettore attivo.</p></fieldset>
    <label className="check"><input type="checkbox" checked={form.shipping_allowed} onChange={e => set('shipping_allowed',e.target.checked)} />Accetto la spedizione</label>
    <label className="check"><input type="checkbox" checked={form.active} onChange={e => set('active',e.target.checked)} />Ricerca periodica attiva</label>
    <div className="form-grid"><Field label="Intervallo in ore (6–168)"><input type="number" min={6} max={168} value={form.interval_hours} onChange={e => set('interval_hours',Number(e.target.value))} /></Field><Field label="Pertinenza minima (0–100)"><input type="number" min={0} max={100} value={form.relevance_threshold} onChange={e => set('relevance_threshold',Number(e.target.value))} /></Field></div>
    {error && <p role="alert" className="error-text">{error}</p>}<footer className="modal-actions">{onDelete && <button type="button" className="danger" disabled={busy} onClick={() => { if (window.confirm('Eliminare il topic e le sue valutazioni? Gli annunci e lo storico restano nel database.')) execute(onDelete); }}>Elimina topic</button>}<button type="button" className="ghost" onClick={onClose}>Annulla</button><button className="primary" disabled={busy}>{busy ? 'Elaborazione…' : 'Salva topic'}</button></footer>
  </form></Modal>;
}

function ImportForm({ onClose, onSave }: { onClose: () => void; onSave: (body: unknown) => Promise<void> }) {
  const [form,setForm] = useState({ listing_url:'',title:'',description:'',price:'',shipping_cost:'',fees:'',town:'',images:'',condition:'',buying_format:'fixed',availability:'unknown',is_shop:false });
  const [busy,setBusy] = useState(false); const [error,setError] = useState('');
  const set = (key: string,value: string | boolean) => setForm(f => ({ ...f,[key]:value }));
  return <Modal title="Valuta un annuncio" onClose={onClose}><p className="muted">Inserisci testo e foto di cui puoi disporre. Il link resta un riferimento: non scarichiamo automaticamente la pagina.</p><form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await onSave({ ...form,source:'manual',price:form.price === '' ? null : Number(form.price),shipping_cost:form.shipping_cost === '' ? null : Number(form.shipping_cost),fees:form.fees === '' ? null : Number(form.fees),images:split(form.images),currency:'EUR' }); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>
    <Field label="Link dell’annuncio"><input type="url" required value={form.listing_url} onChange={e => set('listing_url',e.target.value)} /></Field><Field label="Titolo"><input required maxLength={500} value={form.title} onChange={e => set('title',e.target.value)} /></Field><Field label="Descrizione completa"><textarea rows={5} maxLength={20000} value={form.description} onChange={e => set('description',e.target.value)} /></Field>
    <div className="form-grid thirds">{[['price','Prezzo €'],['shipping_cost','Spedizione €'],['fees','Commissioni €']].map(([key,label]) => <Field key={key} label={label}><input type="number" min={0} step="0.01" placeholder="Non noto" value={form[key as 'price']} onChange={e => set(key,e.target.value)} /></Field>)}</div><p className="muted help">Inserisci 0 solo se il costo è effettivamente nullo. Un campo vuoto resta sconosciuto.</p>
    <Field label="Foto · un URL pubblico per riga, massimo 12"><textarea rows={3} value={form.images} onChange={e => set('images',e.target.value)} /></Field><Field label="Condizioni dichiarate"><input value={form.condition} onChange={e => set('condition',e.target.value)} /></Field><Field label="Località"><input value={form.town} onChange={e => set('town',e.target.value)} /></Field><div className="form-grid"><Field label="Tipo di vendita"><select value={form.buying_format} onChange={e => set('buying_format',e.target.value)}><option value="fixed">Prezzo fisso</option><option value="auction">Asta</option><option value="unknown">Non noto</option></select></Field><Field label="Disponibilità"><select value={form.availability} onChange={e => set('availability',e.target.value)}><option value="unknown">Da verificare</option><option value="active">Disponibile</option><option value="unavailable">Non disponibile</option></select></Field></div><label className="check"><input type="checkbox" checked={form.is_shop} onChange={e => set('is_shop',e.target.checked)} />Venditore professionale</label>
    {error && <p className="error-text" role="alert">{error}</p>}<footer className="modal-actions"><button type="button" className="ghost" onClick={onClose}>Annulla</button><button className="primary" disabled={busy}>{busy ? 'Salvataggio…' : 'Inserisci e valuta'}</button></footer>
  </form></Modal>;
}

function Detail({ listing:l,onClose }: { listing:Listing;onClose:() => void }) {
  const [history,setHistory] = useState<{captured_at:string;listing:Listing}[]>([]); const [historyError,setHistoryError] = useState('');
  useEffect(() => { request<{history:typeof history}>(`/api/listings/${l.id}/history`).then(r => setHistory(r.history)).catch(() => setHistoryError('Storico non disponibile.')); }, [l.id]);
  const a = l.analysis; const r=l.recommendation;
  return <Modal title={l.title} onClose={onClose}>
    {l.images.length > 0 && <div className="gallery">{l.images.map((src,i) => <a href={src} target="_blank" rel="noreferrer" key={src}><img src={src} alt={`Foto ${i+1} dell’annuncio`} referrerPolicy="no-referrer" loading="lazy" /></a>)}</div>}
    <div className="detail-price"><b>{money(r.total_cost ?? l.price,l.currency)}</b><span>{r.total_cost === null ? 'Totale non determinabile' : 'Costo totale'}</span></div><p className="muted">Oggetto {money(l.price,l.currency)} · Spedizione {money(l.shipping_cost,l.currency)} · Commissioni {money(l.fees,l.currency)}</p>
    <div className="score-row"><span>Pertinenza <b>{a?.relevance ?? '—'}/100</b></span><span>Convenienza <b>{r.score === null ? '—' : `${r.score}/100`}</b></span><span>Confidenza <b>{a?.confidence ?? '—'}/100</b></span></div>
    <h3>{r.label}</h3>{r.reasons.map(s => <p key={s}>{s}</p>)}{r.reference !== null && <p>Mediana richieste comparabili: {money(r.reference)} · Differenza: {r.savings_percent}%</p>}
    {r.comparables.length > 0 && <details><summary>Offerte usate per il confronto ({r.comparables.length})</summary>{r.comparables.map(c => <p key={c.id}><a href={c.url} target="_blank" rel="noreferrer">Offerta #{c.id} ↗</a> · {money(c.total_cost)}</p>)}</details>}
    {a ? <><h3>Perché è pertinente</h3><p>{a.reason}</p><p className="muted">Modello: {a.product_key ?? 'Non identificato'} · Configurazione: {a.configuration ?? 'Non identificata'} · Condizioni: {a.condition_grade}</p><TextList title="Condizioni dichiarate" items={a.declared_condition} /><h3>Osservazioni ed evidenze</h3>{a.observations.length === 0 ? <p className="muted">Nessuna osservazione verificabile.</p> : a.observations.map((o,i) => <blockquote key={i}><b>{o.claim}</b><p>{o.detail}</p><small>{o.basis === 'image' ? `Foto ${(o.image_index ?? 0)+1}` : o.basis === 'description' ? 'Descrizione' : 'Dati dell’annuncio'}</small></blockquote>)}<TextList title="Requisiti non soddisfatti" items={a.requirement_failures} /><TextList title="Requisiti da verificare" items={a.requirement_unknowns} /><TextList title="Componenti mancanti" items={a.missing_parts} /><TextList title="Informazioni mancanti" items={a.unknowns} /><TextList title="Segnali da approfondire" items={a.risks} /><TextList title="Domande da fare al venditore" items={a.questions} /><p className="muted">{a.images_examined} foto esaminate · {a.model} · {when(l.evaluated_at)}. La valutazione non certifica il funzionamento.</p></> : <div className="notice">{l.error || 'Annuncio in attesa della valutazione AI.'}</div>}
    <details><summary>Descrizione originale</summary><p className="original-description">{l.description || 'Non disponibile'}</p></details><details><summary>Storico prezzi e verifiche</summary>{historyError || history.map((h,i) => <p key={i}>{when(h.captured_at)} · {money(h.listing.price,h.listing.currency)} · {h.listing.availability}</p>)}</details><p className="muted">Ultimo avvistamento: {when(l.last_seen)}. La mancata ricomparsa in una ricerca non dimostra che sia stato venduto.</p><a className="primary link-button" href={l.listing_url} target="_blank" rel="noreferrer">Apri annuncio originale ↗</a>
  </Modal>;
}
function TextList({ title,items }: {title:string;items:string[]}) { return items.length > 0 ? <section><h3>{title}</h3><ul>{items.map((s,i) => <li key={i}>{s}</li>)}</ul></section> : null; }
