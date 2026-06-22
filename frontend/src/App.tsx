import React, { useState, useRef, useEffect } from 'react';
import {
  UploadCloud, Check, X, CheckCircle,
  Loader2, RefreshCcw, Eye, Download, ArrowLeft, Zap, ChevronDown, ChevronRight,
  Volume2,
} from 'lucide-react';
import logo from '../resources/client_accelerator_logo.png';
import './App.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type IdeaStatus = 'pending' | 'approved' | 'rejected';

interface ProofPoint {
  type: string;
  value: string;
}

interface Idea {
  id: string;
  batch_id: string | null;
  client_id: string;
  hook: string;
  creative_type: string;
  lead_type: string;
  score_impact: number;
  score_confidence: number;
  score_ease: number;
  score_reasoning: string;
  status: IdeaStatus;
  created_at: string | null;
  angle_name: string | null;
  avatar_description: string | null;
  pain_addressed: string | null;
  proof_points: ProofPoint[];
}

interface QualityReviewItem {
  item_number: number;
  item_name: string;
  passed: boolean;
  reason: string;
}

interface QualityReview {
  passed: boolean;
  score: number;
  items: QualityReviewItem[];
  overall_notes: string;
}

interface Script {
  script_id: string;
  content: string;
  status: 'pending_review' | 'passed' | 'failed' | 'error';
  created_at: string | null;
  idea_id: string;
  hook: string;
  creative_type: string;
  lead_type: string;
  score_impact: number;
  score_confidence: number;
  score_ease: number;
  score_reasoning: string | null;
  angle_name: string | null;
  avatar_description: string | null;
  pain_addressed: string | null;
  proof_points: ProofPoint[];
  passed: boolean | null;
  review_score: number | null;
  review_feedback: QualityReview | null;
}

interface IdeasStats {
  total_ideas: number;
  total_batches: number;
  by_status: { approved: number; rejected: number; pending: number };
  total_scripts: number;
  passed_scripts: number;
  failed_scripts: number;
  approved_exemplars_count: number;
}

interface IdeaBatch {
  id: string;
  created_at: string | null;
  idea_count: number;
}

interface ExistingClient {
  id: string;
  name: string;
  brand: string;
  total_ideas: number;
  total_scripts: number;
  created_at: string;
}

interface DedupReportEntry {
  idea_hook: string;
  closest_match_hook: string | null;
  closest_match_id: string | null;
  similarity_score: number;
  threshold: number;
  status: 'kept' | 'rejected';
}

interface DedupBannerData {
  batch_number: number;
  generated: number;
  dedup_rejected: number;
  total_generated: number;
  threshold: number;
  exemplars_used: number;
}

type Step = 'upload' | 'analyzing' | 'review' | 'generating' | 'final';

// ---------------------------------------------------------------------------
// ScriptDetailPanel — fixed popover showing idea details + quality review
// Supports hover-preview (default) and click-to-pin modes
// ---------------------------------------------------------------------------

interface ScriptDetailPanelProps {
  script: Script;
  anchorRect: DOMRect;
  pinned: boolean;
  onClose: () => void;
}

function ScriptDetailPanel({ script, anchorRect, pinned, onClose }: ScriptDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({ visibility: 'hidden' });

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    const popW = el.offsetWidth || 440;
    const popH = el.offsetHeight || 500;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const scrollY = window.scrollY;

    let left = anchorRect.right + 12;
    if (left + popW > vw - 8) left = anchorRect.left - popW - 12;
    if (left < 8) left = 8;

    let top = anchorRect.top + scrollY;
    if (top + popH > scrollY + vh - 8) top = scrollY + vh - popH - 8;
    if (top < scrollY + 8) top = scrollY + 8;

    setStyle({ visibility: 'visible', left, top });
  }, [anchorRect]);

  // Sort quality review items: failed first so problems are immediately visible
  const sortedItems = script.review_feedback?.items
    ? [...script.review_feedback.items].sort((a, b) => Number(a.passed) - Number(b.passed))
    : [];

  return (
    <div className={`script-panel${pinned ? ' pinned' : ''}`} ref={panelRef} style={style}>
      {pinned && (
        <button className="script-panel-close" onClick={onClose} title="Close panel">
          <X size={14} />
        </button>
      )}

      {/* ── Section 1: Idea Details ── */}
      <div className="script-panel-section-title">Idea Details</div>
      <p className="idea-popover-hook">"{script.hook}"</p>
      <div className="idea-popover-grid">
        {script.angle_name && (
          <>
            <span className="idea-popover-label">Angle</span>
            <span className="idea-popover-value">{script.angle_name}</span>
          </>
        )}
        <span className="idea-popover-label">Type</span>
        <span className="idea-popover-value">{script.creative_type}</span>
        <span className="idea-popover-label">Lead</span>
        <span className="idea-popover-value">{script.lead_type}</span>
        {script.avatar_description && (
          <>
            <span className="idea-popover-label">Avatar</span>
            <span className="idea-popover-value">{script.avatar_description}</span>
          </>
        )}
        {script.pain_addressed && (
          <>
            <span className="idea-popover-label">Pain</span>
            <span className="idea-popover-value">{script.pain_addressed}</span>
          </>
        )}
        {script.proof_points && script.proof_points.length > 0 && (
          <>
            <span className="idea-popover-label">Proof</span>
            <span className="idea-popover-value">
              {script.proof_points.map((p, i) => (
                <span key={i} className="idea-popover-proof">• {p.value}</span>
              ))}
            </span>
          </>
        )}
        <span className="idea-popover-label">ICE</span>
        <span className="idea-popover-value idea-popover-ice">
          I{script.score_impact} C{script.score_confidence} E{script.score_ease}
        </span>
        {script.score_reasoning && (
          <>
            <span className="idea-popover-label">Reasoning</span>
            <span className="idea-popover-value idea-popover-reasoning">{script.score_reasoning}</span>
          </>
        )}
      </div>

      {/* ── Section 2: Quality Review ── */}
      {script.review_feedback && (
        <>
          <div className="script-panel-divider" />
          <div className="script-panel-section-title">
            Quality Review
            <span className={`script-panel-score ${script.review_feedback.passed ? 'passed' : 'failed'}`}>
              {script.review_feedback.score}/{sortedItems.length || 11} passed
            </span>
          </div>
          {script.review_feedback.overall_notes && (
            <p className="script-panel-notes">{script.review_feedback.overall_notes}</p>
          )}
          <div className="review-checklist">
            {sortedItems.map(item => (
              <div
                key={item.item_number}
                className={`review-checklist-item ${item.passed ? 'passed' : 'failed'}`}
              >
                <span className="checklist-icon">{item.passed ? '✅' : '❌'}</span>
                <div className="checklist-body">
                  <div className="checklist-name">{item.item_name}</div>
                  <div className="checklist-reason">{item.reason}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {!pinned && (
        <p className="script-panel-pin-hint">Click the status badge to pin this panel</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  const [step, setStep] = useState<Step>('upload');
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [clientId, setClientId] = useState<string | null>(null);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [selectedScript, setSelectedScript] = useState<Script | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [audioGenerating, setAudioGenerating] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Loop state
  const [stats, setStats] = useState<IdeasStats | null>(null);
  const [batches, setBatches] = useState<IdeaBatch[]>([]);
  const [activeBatch, setActiveBatch] = useState<string>('all');
  const [generating, setGenerating] = useState(false);
  const [dedupBanner, setDedupBanner] = useState<DedupBannerData | null>(null);
  const [dedupReport, setDedupReport] = useState<DedupReportEntry[]>([]);
  const [dedupDetailsOpen, setDedupDetailsOpen] = useState(false);
  const [latestBatchId, setLatestBatchId] = useState<string | null>(null);
  const [existingClients, setExistingClients] = useState<ExistingClient[]>([]);
  const bannerTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Script panel state (hover preview + click-to-pin)
  const [hoveredScript, setHoveredScript] = useState<Script | null>(null);
  const [hoverAnchor, setHoverAnchor] = useState<DOMRect | null>(null);
  const [pinnedScript, setPinnedScript] = useState<Script | null>(null);
  const [pinnedAnchor, setPinnedAnchor] = useState<DOMRect | null>(null);
  const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Derived state -------------------------------------------------------

  const approvedIdeas = ideas.filter(i => i.status === 'approved');
  const hasApproved = approvedIdeas.length > 0;

  const filteredIdeas = ideas.filter(idea => {
    if (activeBatch === 'all') return true;
    if (activeBatch === 'pending') return idea.status === 'pending';
    return idea.batch_id === activeBatch;
  });

  const scriptMap = scripts.reduce<Record<string, Script>>((map, s) => {
    if (!map[s.idea_id]) map[s.idea_id] = s;
    return map;
  }, {});

  const passedScripts = scripts.filter(s => s.status === 'passed');
  const hasPendingScripts =
    scripts.some(s => s.status === 'pending_review') ||
    (step === 'final' && approvedIdeas.some(i => !scriptMap[i.id]));

  // True when there's at least one dedup comparison to show
  const hasDedupData = dedupReport.some(e => e.closest_match_hook !== null);

  // ---- Data fetchers -------------------------------------------------------

  const fetchIdeas = async (cid?: string) => {
    const id = cid || clientId;
    if (!id) return;
    try {
      const res = await fetch(`/api/clients/${id}/ideas`);
      if (res.ok) setIdeas(await res.json());
    } catch (e) { console.error('Failed to fetch ideas:', e); }
  };

  const fetchStats = async (cid?: string) => {
    const id = cid || clientId;
    if (!id) return;
    try {
      const res = await fetch(`/api/clients/${id}/ideas/stats`);
      if (res.ok) setStats(await res.json());
    } catch (e) { console.error('Failed to fetch stats:', e); }
  };

  const fetchBatches = async (cid?: string) => {
    const id = cid || clientId;
    if (!id) return;
    try {
      const res = await fetch(`/api/clients/${id}/ideas/batches`);
      if (res.ok) setBatches(await res.json());
    } catch (e) { console.error('Failed to fetch batches:', e); }
  };

  const fetchScripts = async (cid?: string) => {
    const id = cid || clientId;
    if (!id) return;
    try {
      const res = await fetch(`/api/clients/${id}/scripts`);
      if (res.ok) setScripts(await res.json());
    } catch (err) { console.error('Failed to fetch scripts:', err); }
  };

  const generateAudio = async (scriptId: string, hookNumber: number) => {
    const key = `${scriptId}-${hookNumber}`;
    setAudioGenerating(prev => ({ ...prev, [key]: true }));
    try {
      const res = await fetch(`/api/scripts/${scriptId}/audio?hook_number=${hookNumber}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `Audio generation failed: ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrls(prev => ({ ...prev, [key]: url }));
    } catch (err) {
      console.error('Audio generation failed:', err);
    } finally {
      setAudioGenerating(prev => ({ ...prev, [key]: false }));
    }
  };

  // ---- Consume generation response ----------------------------------------

  const applyGenResult = (data: Record<string, unknown>) => {
    const report = (data.dedup_report as DedupReportEntry[]) || [];
    setDedupReport(report);
    setDedupDetailsOpen(false);

    const apiStats = data.stats as { total_generated: number; kept: number; rejected_dedup: number } | undefined;
    const threshold = report[0]?.threshold ?? 0.85;

    setDedupBanner({
      batch_number: data.batch_number as number,
      generated: data.generated as number,
      dedup_rejected: (data.dedup_rejected as unknown[])?.length || 0,
      total_generated: apiStats?.total_generated ?? (data.generated as number),
      threshold,
      exemplars_used: (data.learning_context as { exemplars_used: number })?.exemplars_used || 0,
    });

    if (bannerTimeout.current) clearTimeout(bannerTimeout.current);
    bannerTimeout.current = setTimeout(() => setDedupBanner(null), 12000);
  };

  // ---- Check for returning client on mount --------------------------------

  useEffect(() => {
    fetch('/api/clients')
      .then(r => r.ok ? r.json() : [])
      .then((data: ExistingClient[]) => setExistingClients(data))
      .catch(() => {});
  }, []);

  // ---- Upload handlers -----------------------------------------------------

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setDragOver(false); };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    if (e.dataTransfer.files?.length) handleFileUpload(e.dataTransfer.files[0]);
  };
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) handleFileUpload(e.target.files[0]);
  };

  const handleFileUpload = async (selectedFile: File) => {
    setFile(selectedFile);
    setUploadError(null);
    setStep('analyzing');
    const formData = new FormData();
    formData.append('file', selectedFile);
    try {
      const uploadRes = await fetch('/api/process-reference-pack', { method: 'POST', body: formData });
      if (!uploadRes.ok) {
        const err = await uploadRes.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `Server error: ${uploadRes.status}`);
      }
      const uploadData = await uploadRes.json();
      const firstClientId: string = uploadData.client_ids?.[0];
      if (!firstClientId) throw new Error('No client ID returned from upload');
      setClientId(firstClientId);

      const genRes = await fetch(`/api/clients/${firstClientId}/ideas/generate?n=12`, { method: 'POST' });
      if (!genRes.ok) {
        const err = await genRes.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `Idea generation failed: ${genRes.status}`);
      }
      const genData = await genRes.json();
      setLatestBatchId(genData.batch_id);
      applyGenResult(genData);

      await Promise.all([fetchIdeas(firstClientId), fetchStats(firstClientId), fetchBatches(firstClientId)]);
      setActiveBatch(genData.batch_id);
      setStep('review');
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Failed to process file');
      setStep('upload');
    }
  };

  // ---- Continue with existing client ---------------------------------------

  const handleContinueWithClient = async (client: ExistingClient) => {
    setClientId(client.id);
    await Promise.all([fetchIdeas(client.id), fetchStats(client.id), fetchBatches(client.id)]);
    setActiveBatch('all');
    setStep('review');
  };

  // ---- Generate more ideas -------------------------------------------------

  const handleGenerateMore = async () => {
    if (!clientId || generating) return;
    setGenerating(true);
    try {
      const res = await fetch(`/api/clients/${clientId}/ideas/generate?n=12`, { method: 'POST' });
      if (!res.ok) throw new Error('Generation failed');
      const data = await res.json();
      setLatestBatchId(data.batch_id);
      applyGenResult(data);
      await Promise.all([fetchIdeas(), fetchStats(), fetchBatches()]);
      setActiveBatch(data.batch_id);
    } catch (err) {
      console.error('Generation failed:', err);
    } finally {
      setGenerating(false);
    }
  };

  // ---- Idea status update --------------------------------------------------

  const updateIdeaStatus = async (id: string, status: IdeaStatus) => {
    try {
      const res = await fetch(`/api/ideas/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error('Status update failed');
      setIdeas(prev => prev.map(idea => idea.id === id ? { ...idea, status } : idea));
      fetchStats();
    } catch (err) { console.error('Failed to update idea status:', err); }
  };

  // ---- Script fetching & polling -------------------------------------------

  useEffect(() => {
    if (step === 'final') fetchScripts();
  }, [step, clientId]);

  useEffect(() => {
    if (step !== 'final' || !hasPendingScripts) return;
    const interval = setInterval(fetchScripts, 5000);
    return () => clearInterval(interval);
  }, [step, hasPendingScripts, clientId]);

  // ---- Navigation ----------------------------------------------------------

  const viewScripts = () => { setStep('generating'); setTimeout(() => setStep('final'), 600); };
  const backToIdeas = () => setStep('review');

  // ---- Script panel (hover + pin) -----------------------------------------

  const handleRowMouseEnter = (e: React.MouseEvent, script: Script | undefined) => {
    if (!script || pinnedScript) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    hoverTimeout.current = setTimeout(() => { setHoveredScript(script); setHoverAnchor(rect); }, 200);
  };

  const handleRowMouseLeave = () => {
    if (hoverTimeout.current) clearTimeout(hoverTimeout.current);
    if (!pinnedScript) { setHoveredScript(null); setHoverAnchor(null); }
  };

  const handleStatusCellClick = (e: React.MouseEvent, script: Script | undefined) => {
    if (!script) return;
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    if (pinnedScript?.script_id === script.script_id) {
      setPinnedScript(null); setPinnedAnchor(null);
    } else {
      setPinnedScript(script); setPinnedAnchor(rect);
      setHoveredScript(null); setHoverAnchor(null);
    }
  };

  // ---- Export --------------------------------------------------------------

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    if (!clientId) return;
    setExporting(true); setExportError(null);
    try {
      const response = await fetch(`/api/clients/${clientId}/scripts/export-to-gdocs`, { method: 'POST' });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Export failed' }));
        throw new Error(err.detail || `Export failed: ${response.status}`);
      }
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/vnd.openxmlformats')) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `scripts_${new Date().toISOString().split('T')[0]}.docx`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      } else {
        const data = await response.json();
        if (data.url) window.open(data.url, '_blank');
      }
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed');
    } finally { setExporting(false); }
  };

  // ---- Reset ---------------------------------------------------------------

  const restartProcess = () => {
    setFile(null); setIdeas([]); setClientId(null); setUploadError(null);
    setScripts([]); setSelectedScript(null); setModalOpen(false);
    setStats(null); setBatches([]); setActiveBatch('all');
    setDedupBanner(null); setDedupReport([]); setDedupDetailsOpen(false);
    setLatestBatchId(null); setPinnedScript(null); setPinnedAnchor(null);
    Object.values(audioUrls).forEach(url => URL.revokeObjectURL(url));
    setAudioUrls({}); setAudioGenerating({});
    setStep('upload');
    fetch('/api/clients').then(r => r.ok ? r.json() : []).then(setExistingClients).catch(() => {});
  };

  // ---- Script status badge -------------------------------------------------

  const ScriptStatusBadge = ({ script }: { script: Script | undefined }) => {
    if (!script) return (
      <span className="delivery-status delivery-status--pending">
        <Loader2 size={13} className="spinner-inline" /> Generating...
      </span>
    );
    if (script.status === 'pending_review') return (
      <span className="delivery-status delivery-status--pending">
        <Loader2 size={13} className="spinner-inline" /> Reviewing...
      </span>
    );
    if (script.status === 'passed') return (
      <span className="delivery-status delivery-status--passed">
        <CheckCircle size={13} /> Passed
      </span>
    );
    if (script.status === 'failed') return (
      <span className="delivery-status delivery-status--failed">
        <X size={13} /> Failed ({script.review_score ?? '?'}/11)
      </span>
    );
    return (
      <span className="delivery-status delivery-status--error">
        <X size={13} /> Error
      </span>
    );
  };

  // ---- Render --------------------------------------------------------------

  return (
    <div className="app-container">
      <header className="header">
        <div className="logo-wrapper">
          <img src={logo} alt="Client Accelerator" className="logo" />
        </div>
        <p>Upload your brief. Review ideas. Generate winning scripts.</p>
      </header>

      {/* ── UPLOAD ── */}
      {step === 'upload' && (
        <>
          {uploadError && (
            <div className="error-banner"><X size={18} /><span>{uploadError}</span></div>
          )}
          {existingClients.length > 0 && (
            <div className="existing-client-card">
              <div className="existing-client-info">
                <div className="existing-client-name">{existingClients[0].name}</div>
                <div className="existing-client-meta">
                  {existingClients[0].brand} · {existingClients[0].total_ideas} ideas
                  {existingClients[0].total_scripts > 0 && ` · ${existingClients[0].total_scripts} scripts`}
                </div>
              </div>
              <button className="btn-primary" onClick={() => handleContinueWithClient(existingClients[0])}>
                Continue →
              </button>
            </div>
          )}
          <div
            className={`upload-card ${dragOver ? 'drag-over' : ''}`}
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloud size={48} className="upload-icon" />
            <h2 className="upload-title">
              {existingClients.length > 0 ? 'Upload New Client' : 'Upload your reference pack'}
            </h2>
            <p className="upload-subtitle">Drag and drop your PDF or click to browse.</p>
            <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".pdf,.docx,.txt" />
            <button className="btn-primary">Browse Files</button>
          </div>
        </>
      )}

      {/* ── ANALYZING ── */}
      {step === 'analyzing' && (
        <div className="loading-state">
          <Loader2 size={48} className="spinner" />
          <h2>Processing your reference pack...</h2>
          <p className="upload-subtitle" style={{ marginTop: '0.5rem' }}>
            {file?.name} — extracting data, saving to database, and generating ideas.
          </p>
        </div>
      )}

      {/* ── REVIEW / IDEAS DASHBOARD ── */}
      {step === 'review' && (
        <div>
          {/* Dashboard header */}
          <div className="ideas-dashboard-header">
            <div>
              <h2>Ideas Dashboard</h2>
              {stats && (
                <div className="stats-line">
                  {stats.total_batches > 0 && <span>Run {stats.total_batches}</span>}
                  <span>{stats.total_ideas} total ideas</span>
                  <span className="stats-approved">{stats.by_status.approved} approved</span>
                  {stats.passed_scripts > 0 && (
                    <span className="stats-passed">{stats.passed_scripts} scripts passed</span>
                  )}
                </div>
              )}
            </div>
            <div className="dashboard-actions">
              <button className="btn-secondary" onClick={viewScripts} disabled={!hasApproved}
                title={!hasApproved ? 'Approve at least one idea first' : undefined}>
                View Scripts →
              </button>
              <button className="btn-primary" onClick={handleGenerateMore} disabled={generating}>
                {generating
                  ? <><Loader2 size={16} className="spinner-inline" /> Generating...</>
                  : <><Zap size={16} /> Generate More Ideas</>}
              </button>
            </div>
          </div>

          {/* Dedup run banner */}
          {dedupBanner && (
            <div className="run-banner">
              <div className="run-banner-text">
                <strong>Run {dedupBanner.batch_number} complete:</strong>{' '}
                {dedupBanner.total_generated > 0
                  ? <>Generated {dedupBanner.total_generated} → {dedupBanner.generated} kept
                      {dedupBanner.dedup_rejected > 0 && <>, {dedupBanner.dedup_rejected} rejected as too similar (threshold: {Math.round(dedupBanner.threshold * 100)}%)</>}.
                    </>
                  : <>{dedupBanner.generated} ideas generated.</>}
                {dedupBanner.exemplars_used > 0 && (
                  <> Learning from {dedupBanner.exemplars_used} approved winner{dedupBanner.exemplars_used !== 1 ? 's' : ''}.</>
                )}
                {hasDedupData && (
                  <button className="run-banner-toggle" onClick={() => setDedupDetailsOpen(v => !v)}>
                    {dedupDetailsOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    {dedupDetailsOpen ? 'Hide details' : 'Show similarity details'}
                  </button>
                )}
              </div>
              <button className="run-banner-dismiss" onClick={() => setDedupBanner(null)}><X size={14} /></button>
            </div>
          )}

          {/* Expandable dedup details table */}
          {dedupDetailsOpen && hasDedupData && (
            <div className="dedup-details-section">
              <div className="dedup-table-header">
                <span>Generated idea</span>
                <span>Closest existing</span>
                <span>Sim</span>
                <span>Result</span>
              </div>
              {[...dedupReport]
                .sort((a, b) => (a.status === 'rejected' ? -1 : 1) - (b.status === 'rejected' ? -1 : 1))
                .map((entry, i) => (
                  <div key={i} className={`dedup-row dedup-row--${entry.status}`}>
                    <span className="dedup-hook" title={entry.idea_hook}>
                      {entry.idea_hook.length > 55 ? entry.idea_hook.slice(0, 55) + '…' : entry.idea_hook}
                    </span>
                    <span className="dedup-match" title={entry.closest_match_hook ?? ''}>
                      {entry.closest_match_hook
                        ? (entry.closest_match_hook.length > 55
                          ? entry.closest_match_hook.slice(0, 55) + '…'
                          : entry.closest_match_hook)
                        : '—'}
                    </span>
                    <span className="dedup-sim">
                      {entry.closest_match_hook ? `${Math.round(entry.similarity_score * 100)}%` : '—'}
                    </span>
                    <span className={`dedup-badge dedup-badge--${entry.status}`}>
                      {entry.status.toUpperCase()}
                    </span>
                  </div>
                ))}
            </div>
          )}

          {/* Batch / run filter tabs */}
          {batches.length > 1 && (
            <div className="batch-tabs">
              <button className={`tab-btn ${activeBatch === 'all' ? 'active' : ''}`} onClick={() => setActiveBatch('all')}>
                All Ideas
              </button>
              {batches.map((b, i) => (
                <button key={b.id} className={`tab-btn ${activeBatch === b.id ? 'active' : ''}`} onClick={() => setActiveBatch(b.id)}>
                  Run {i + 1} ({b.idea_count})
                </button>
              ))}
              <button className={`tab-btn ${activeBatch === 'pending' ? 'active' : ''}`} onClick={() => setActiveBatch('pending')}>
                Pending Only
              </button>
            </div>
          )}

          {/* Ideas list */}
          <div className="ideas-list">
            {filteredIdeas.length === 0 && (
              <div className="empty-state">No ideas match the current filter.</div>
            )}
            {filteredIdeas.map((idea) => {
              const dedupEntry = dedupReport.find(e => e.idea_hook === idea.hook);
              const showSimPill = dedupEntry?.closest_match_hook != null;
              return (
                <div key={idea.id} className={`idea-card ${idea.status !== 'pending' ? idea.status : ''}`}>
                  <div className="idea-hook-row">
                    <div className="idea-hook">{idea.hook}</div>
                    <div className="idea-hook-badges">
                      {idea.batch_id === latestBatchId && latestBatchId && dedupBanner && (
                        <span className="badge-new">NEW</span>
                      )}
                      {showSimPill && (
                        <span
                          className={`sim-pill ${dedupEntry!.status === 'rejected' ? 'sim-pill--rejected' : ''}`}
                          title={`Closest existing idea: "${dedupEntry!.closest_match_hook}"`}
                        >
                          Sim: {Math.round(dedupEntry!.similarity_score * 100)}%
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="idea-tags">
                    <span className="idea-tag tag-creative">{idea.creative_type}</span>
                    <span className="idea-tag tag-lead">{idea.lead_type}</span>
                  </div>

                  <div className="idea-details">
                    {idea.angle_name && (
                      <div className="idea-detail-row">
                        <span className="detail-label">Angle</span>
                        <span className="detail-value">{idea.angle_name}</span>
                      </div>
                    )}
                    {idea.avatar_description && (
                      <div className="idea-detail-row">
                        <span className="detail-label">Avatar</span>
                        <span className="detail-value">{idea.avatar_description}</span>
                      </div>
                    )}
                    {idea.pain_addressed && (
                      <div className="idea-detail-row">
                        <span className="detail-label">Pain</span>
                        <span className="detail-value">{idea.pain_addressed}</span>
                      </div>
                    )}
                    {idea.proof_points.length > 0 && (
                      <div className="idea-detail-row">
                        <span className="detail-label">Proof</span>
                        <span className="detail-value">
                          {idea.proof_points.map((p, i) => (
                            <span key={i} className="proof-chip"><em>{p.type}:</em> {p.value}</span>
                          ))}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="idea-meta">
                    <div className="ice-scores ice-tooltip" data-tooltip={idea.score_reasoning}>
                      <div className="score-badge"><span>I</span> <strong>{idea.score_impact}</strong></div>
                      <div className="score-badge"><span>C</span> <strong>{idea.score_confidence}</strong></div>
                      <div className="score-badge"><span>E</span> <strong>{idea.score_ease}</strong></div>
                      <span className="ice-label">ICE — hover for reasoning</span>
                    </div>
                    {idea.status === 'pending' ? (
                      <div className="idea-actions">
                        <button className="btn-reject" onClick={() => updateIdeaStatus(idea.id, 'rejected')}>
                          <X size={18} /> Reject
                        </button>
                        <button className="btn-approve" onClick={() => updateIdeaStatus(idea.id, 'approved')}>
                          <Check size={18} /> Approve
                        </button>
                      </div>
                    ) : (
                      <div className={`status-badge ${idea.status}`}>
                        {idea.status === 'approved' ? <CheckCircle size={18} /> : <X size={18} />}
                        {idea.status.charAt(0).toUpperCase() + idea.status.slice(1)}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── GENERATING (brief transition) ── */}
      {step === 'generating' && (
        <div className="loading-state">
          <Loader2 size={48} className="spinner" />
          <h2>Loading Script Delivery...</h2>
          <p className="upload-subtitle" style={{ marginTop: '0.5rem' }}>
            {approvedIdeas.length} approved idea{approvedIdeas.length !== 1 ? 's' : ''} queued for script generation.
          </p>
        </div>
      )}

      {/* ── FINAL / DELIVERY VIEW ── */}
      {step === 'final' && (
        <div>
          <div className="ideas-header" style={{ marginBottom: '1.5rem' }}>
            <div>
              <h2>Script Delivery</h2>
              <p className="upload-subtitle" style={{ marginBottom: 0 }}>
                {hasPendingScripts
                  ? 'Scripts are generating — refreshing every 5 seconds...'
                  : `${passedScripts.length} of ${approvedIdeas.length} script${approvedIdeas.length !== 1 ? 's' : ''} passed quality review`}
              </p>
              {exportError && <p className="export-error"><X size={13} /> {exportError}</p>}
            </div>
            <div className="dashboard-actions">
              <button className="btn-secondary" onClick={backToIdeas}>
                <ArrowLeft size={16} /> Back to Ideas
              </button>
              <button className="btn-primary" onClick={handleExport}
                disabled={passedScripts.length === 0 || exporting}
                title={passedScripts.length === 0 ? 'No passing scripts yet' : undefined}>
                {exporting
                  ? <><Loader2 size={16} className="spinner-inline" /> Exporting...</>
                  : <><Download size={16} /> Export to Google Docs</>}
              </button>
            </div>
          </div>

          <div className="delivery-table">
            <div className="delivery-table-header">
              <span>Hook</span>
              <span>Angle / Type</span>
              <span>ICE</span>
              <span>Status</span>
              <span></span>
            </div>
            {approvedIdeas.map((idea) => {
              const script = scriptMap[idea.id];
              const isPinned = pinnedScript?.script_id === script?.script_id;
              return (
                <div
                  key={idea.id}
                  className="delivery-row"
                  onMouseEnter={(e) => handleRowMouseEnter(e, script)}
                  onMouseLeave={handleRowMouseLeave}
                >
                  <div className="delivery-hook">
                    {(idea.hook || '').length > 80 ? idea.hook.substring(0, 80) + '...' : idea.hook}
                  </div>
                  <div className="delivery-meta">
                    {idea.angle_name && <span className="idea-tag tag-lead">{idea.angle_name}</span>}
                    <span className="idea-tag tag-creative">{idea.creative_type}</span>
                  </div>
                  <div className="delivery-ice">
                    I{idea.score_impact} C{idea.score_confidence} E{idea.score_ease}
                  </div>
                  <div
                    className={`delivery-status-cell${script ? ' delivery-status-cell--clickable' : ''}`}
                    onClick={(e) => handleStatusCellClick(e, script)}
                    title={script ? (isPinned ? 'Click to unpin' : 'Click to pin details') : undefined}
                  >
                    <ScriptStatusBadge script={script} />
                    {isPinned && <span className="pin-indicator" title="Pinned">📌</span>}
                  </div>
                  <div className="delivery-actions">
                    {script && (
                      <button className="btn-view" onClick={() => { setSelectedScript(script); setModalOpen(true); }}>
                        <Eye size={14} /> View
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {scripts.some(s => s.status === 'failed') && !hasPendingScripts && (
            <div className="failed-hint">
              Some scripts didn't pass quality review.{' '}
              <button className="failed-hint-link" onClick={backToIdeas}>
                Generate more ideas →
              </button>
            </div>
          )}

          <div className="restart-section">
            <button className="btn-reject" onClick={restartProcess} style={{ margin: '0 auto' }}>
              <RefreshCcw size={18} /> Start New Campaign
            </button>
          </div>
        </div>
      )}

      {/* ── SCRIPT PANEL (hover preview or pinned) ── */}
      {pinnedScript && pinnedAnchor && (
        <ScriptDetailPanel
          script={pinnedScript}
          anchorRect={pinnedAnchor}
          pinned={true}
          onClose={() => { setPinnedScript(null); setPinnedAnchor(null); }}
        />
      )}
      {!pinnedScript && hoveredScript && hoverAnchor && (
        <ScriptDetailPanel
          script={hoveredScript}
          anchorRect={hoverAnchor}
          pinned={false}
          onClose={() => {}}
        />
      )}

      {/* ── SCRIPT MODAL ── */}
      {modalOpen && selectedScript && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-header-text">
                <h3 className="modal-title">
                  {(selectedScript.hook || '').length > 80
                    ? selectedScript.hook.substring(0, 80) + '...'
                    : selectedScript.hook}
                </h3>
                <div className="modal-meta">
                  {selectedScript.angle_name && <span className="idea-tag tag-lead">{selectedScript.angle_name}</span>}
                  <span className="idea-tag tag-creative">{selectedScript.creative_type}</span>
                  <span className="idea-tag tag-lead">{selectedScript.lead_type}</span>
                  <span className="modal-ice">
                    I{selectedScript.score_impact} C{selectedScript.score_confidence} E{selectedScript.score_ease}
                  </span>
                </div>
              </div>
              <button className="modal-close" onClick={() => setModalOpen(false)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              <div className="modal-section">
                <h4 className="modal-section-title">Script</h4>
                <pre className="script-content">{selectedScript.content}</pre>
              </div>
              {selectedScript.review_feedback && (
                <div className="modal-section">
                  <h4 className="modal-section-title">
                    Quality Review —{' '}
                    {selectedScript.review_feedback.passed
                      ? <span className="review-verdict passed">Passed</span>
                      : <span className="review-verdict failed">Failed</span>}
                    {' '}
                    <span className="review-score">
                      ({selectedScript.review_score ?? selectedScript.review_feedback.score}/11)
                    </span>
                  </h4>
                  {selectedScript.review_feedback.overall_notes && (
                    <p className="review-overall-notes">{selectedScript.review_feedback.overall_notes}</p>
                  )}
                  <div className="review-items">
                    {(selectedScript.review_feedback.items || []).map((item) => (
                      <div key={item.item_number}
                        className={`review-item ${item.passed ? 'review-item--passed' : 'review-item--failed'}`}>
                        <div className="review-item-header">
                          <span className="review-item-num">{item.item_number}.</span>
                          <span className="review-item-name">{item.item_name}</span>
                          <span className="review-item-verdict">
                            {item.passed ? <CheckCircle size={14} /> : <X size={14} />}
                          </span>
                        </div>
                        <p className="review-item-reason">{item.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Voiceovers ── */}
              <div className="modal-section">
                <h4 className="modal-section-title">
                  <Volume2 size={14} /> Voiceovers
                </h4>
                <p className="voiceover-hint">
                  Each hook is combined with the full body and synthesized with Gemini TTS.
                  Generation takes ~30–60 s per hook.
                </p>
                <div className="audio-hooks">
                  {[1, 2, 3].map(hookNum => {
                    const key = `${selectedScript.script_id}-${hookNum}`;
                    const url = audioUrls[key];
                    const loading = !!audioGenerating[key];
                    return (
                      <div key={hookNum} className="audio-hook-row">
                        <span className="audio-hook-label">Hook {hookNum}</span>
                        {url ? (
                          <audio controls src={url} className="audio-player" />
                        ) : (
                          <button
                            className="btn-generate-audio"
                            onClick={() => generateAudio(selectedScript.script_id, hookNum)}
                            disabled={loading}
                          >
                            {loading
                              ? <><Loader2 size={13} className="spinner-inline" /> Generating...</>
                              : <><Volume2 size={13} /> Generate</>}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
