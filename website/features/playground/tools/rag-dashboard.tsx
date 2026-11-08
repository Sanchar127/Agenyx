'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  BarChart3,
  Bot,
  Check,
  Copy,
  Document,
  Globe,
  RefreshCw,
  Search,
  Shield,
  TrendingUp,
  X,
} from 'lucide-react';

const AGENTYX_API_BASE =
  process.env.NEXT_PUBLIC_AGENYX_API_URL || 'http://localhost:8004';

interface RagChunk {
  index: number;
  document_id: string;
  chunk_index: number;
  content: string;
  score: number;
  search_type: string;
  metadata: Record<string, any>;
  content_preview: string;
}

interface RagResponse {
  answer: string;
  model: string;
  provider: string;
  sources: RagChunk[];
  chunks_retrieved: number;
  usage: Record<string, any>;
  timing_ms: {
    embed: number;
    retrieve: number;
    generate: number;
    total: number;
  };
}

interface DocumentUpsertChunk {
  chunk_index: number;
  content: string;
  embedding: number[];
  metadata?: Record<string, any>;
}

interface RagDoc {
  id: string;
  content: string;
  metadata: Record<string, any>;
  content_type?: string;
}

const DOCUMENT_STORE_KEY = 'agenyx-rag-documents';

function loadDocuments(): RagDoc[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(DOCUMENT_STORE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is RagDoc =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as RagDoc).id === 'string' &&
        typeof (item as RagDoc).content === 'string',
    );
  } catch {
    return [];
  }
}

function saveDocuments(docs: RagDoc[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(DOCUMENT_STORE_KEY, JSON.stringify(docs));
  } catch {
    // Storage can be unavailable (private mode); ingestion still works in-memory.
  }
}

export function RagDocumentUpload() {
  const [documents, setDocuments] = useState<RagDoc[]>(loadDocuments);
  const [content, setContent] = useState('');
  const [contentType, setContentType] = useState('text/plain');
  const [metadata, setMetadata] = useState<Record<string, any>>({});
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<string | null>(null);

  const handleUpload = async () => {
    if (!content.trim()) return;

    setIsUploading(true);
    setError(null);

    try {
      const response = await fetch(
        `${AGENTYX_API_BASE}/v1/documents/upload`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content,
            content_type: contentType,
            metadata,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      const data = await response.json();
      setLastUploaded(data.document_id);

      setDocuments((prev) => [
        ...prev,
        {
          id: data.document_id,
          content,
          content_type: contentType,
          metadata,
        },
      ]);
      setContent('');
      setMetadata({});
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Upload failed',
      );
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='flex items-center gap-2 mb-4'>
        <Document className='h-5 w-5' />
        <h3 className='text-sm font-semibold text-fd-foreground'>Upload Document</h3>
      </div>

      {error && (
        <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500'>
          {error}
        </div>
      )}

      <div className='grid gap-3'>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder='Paste document text here...'
          rows={4}
          className='w-full rounded-lg border border-fd-border bg-fd-card px-3 py-2 text-sm text-fd-foreground placeholder:text-fd-muted-foreground focus:ring-2 focus:ring-emerald-500/50 focus:outline-none disabled:opacity-60 disabled:bg-fd-muted'
          disabled={isUploading}
        />
        <div className='flex flex-wrap gap-2'>
          <input
            type='text'
            value={contentType}
            onChange={(e) => setContentType(e.target.value)}
            placeholder='content type'
            className='w-full rounded-lg border border-fd-border bg-fd-card px-3 py-2 text-sm text-fd-foreground focus:ring-2 focus:ring-emerald-500/50 focus:outline-none disabled:opacity-60 disabled:bg-fd-muted'
            disabled={isUploading}
          />
          <input
            type='text'
            value={metadata.key || ''}
            onChange={(e) => setMetadata({ ...metadata, key: e.target.value })}
            placeholder='metadata key'
            className='w-full rounded-lg border border-fd-border bg-fd-card px-3 py-2 text-sm text-fd-foreground focus:ring-2 focus:ring-emerald-500/50 focus:outline-none disabled:opacity-60 disabled:bg-fd-muted'
            disabled={isUploading}
          />
          <input
            type='text'
            value={metadata.value || ''}
            onChange={(e) => setMetadata({ ...metadata, value: e.target.value })}
            placeholder='metadata value'
            className='w-full rounded-lg border border-fd-border bg-fd-card px-3 py-2 text-sm text-fd-foreground focus:ring-2 focus:ring-emerald-500/50 focus:outline-none disabled:opacity-60 disabled:bg-fd-muted'
            disabled={isUploading}
          />
        </div>
      </div>

      <button
        onClick={handleUpload}
        disabled={!content.trim() || isUploading}
        className='w-full flex items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50'
      >
        {isUploading ? (
          <>
            <svg className='h-4 w-4 animate-spin' viewBox='0 0 24 24'>
              <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'></circle>
              <path className='opacity-75' fill='currentColor' fill-rule='evenodd' d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291a7.962 7.962 0 014-4v4a7.962 7.962 0 01-4-4z' />
            </svg>
            Uploading…
          </>
        ) : (
          <>Upload Document</>
        )}
      </button>

      {lastUploaded && (
        <div className='flex items-center gap-2 mt-2 text-xs text-emerald-600 bg-emerald-500/10 px-3 py-2 rounded-lg border border-emerald-500/20'>
          <Check className='h-3.5 w-3.5' />
          <span>Document uploaded: {lastUploaded}</span>
        </div>
      )}

      {documents.length > 0 && (
        <div className='mt-4 border-t border-fd-border pt-4'>
          <h4 className='text-xs font-semibold text-fd-muted-foreground uppercase tracking-wider'>Stored Documents ({documents.length})</h3>
          <div className='flex gap-2 overflow-x-auto px-1 mt-2'>
            {documents.map((doc) => (
              <button
                key={doc.id}
                type='button'
                className='shrink-0 inline-flex items-center gap-2 rounded-lg bg-emerald-500/10 px-2 py-1.5 text-xs font-medium text-emerald-700 border border-emerald-500/20'
              >
                <span className='text-[0.625rem] font-mono text-emerald-500'>{doc.id.slice(0, 8)}…</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function RagChatPanel() {
  const [query, setQuery] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<RagResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isRunning) return;

    setIsRunning(true);
    setError(null);

    try {
      const response = await fetch(`${AGENTYX_API_BASE}/v1/rag/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Agenyx-Service-Key': localStorage.getItem('AGENYX_API_KEY') || '',
        },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail?.message || `Request failed: ${response.status}`);
      }

      const data: RagResponse = await response.json();
      setResult(data);
      setQuery('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setIsRunning(false);
      setTimeout(scrollToBottom, 50);
    }
  };

  return (
    <div className='flex flex-col h-full gap-4'>
      <div className='flex items-center gap-2 mb-3'>
        <Shield className='h-5 w-5' />
        <h3 className='text-sm font-semibold text-fd-foreground'>RAG Query</h3>
      </div>

      {error && (
        <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500'>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className='flex flex-col gap-3'>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='Ask a question about your documents…'
          rows={2}
          className='w-full rounded-lg border border-fd-border bg-fd-card px-3 py-2 text-sm text-fd-foreground placeholder:text-fd-muted-foreground focus:ring-2 focus:ring-emerald-500/50 focus:outline-none disabled:opacity-60 disabled:bg-fd-muted'
          disabled={isRunning}
        />
        <button
          type='submit'
          disabled={!query.trim() || isRunning}
          className='w-full flex items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50'
        >
          {isRunning ? (
            <>
              <svg className='h-4 w-4 animate-spin' viewBox='0 0 24 24'>
                <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'></circle>
                <path className='opacity-75' fill='currentColor' fill-rule='evenodd' d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291a7.962 7.962 0 014-4v4a7.962 7.962 0 01-4-4z' />
              </svg>
              Processing…
            </>
          ) : (
            <>Ask</>
          )}
        </button>
      </form>

      {result && (
        <div className='flex flex-col gap-3 overflow-y-auto flex-1 min-h-[200px] max-h-[400px]' ref={messagesRef}>
          <div className='flex items-start gap-2'>
            <div className='flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 shrink-0'>
              <Bot className='h-3.5 w-3.5' />
            </div>
            <div className='flex-1 rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-fd-foreground break-words'>
              {result.answer}
            </div>
          </div>
          <div className='mt-2 pt-2 border-t border-fd-border/50'>
            <p className='text-xs text-fd-muted-foreground mb-2'>Sources ({result.chunks_retrieved})</p>
            <div className='flex gap-2 overflow-x-auto px-2'>
              {result.sources.map((src, i) => (
                <button
                  key={i}
                  type='button'
                  className='shrink-0 inline-flex items-center gap-1 rounded-md bg-fd-card px-2 py-1 text-xs text-fd-foreground border border-fd-border hover:bg-fd-muted'
                >
                  <span className='text-[0.625rem] font-mono text-fd-muted-foreground'>{src.document_id.slice(0, 8)}…</span>
                  <span className='bg-emerald-500/10 text-emerald-500 text-[0.55rem] px-1 py-0.5 rounded'>{(src.score * 100).toFixed(0)}%</span>
                </button>
              ))}
            </div>
            <div className='mt-2 flex items-center gap-2 text-xs text-fd-muted-foreground'>
              <span className='flex items-center gap-1'>
                <BarChart3 className='h-3 w-3' />
                {result.timing_ms.total}ms
              </span>
              <span className='flex items-center gap-1'>
                <Globe className='h-3 w-3' />
                {result.provider}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function RagSystemStats() {
  return (
    <div className='rounded-lg border border-fd-border bg-fd-card p-3'>
      <h3 className='text-xs font-semibold text-fd-muted-foreground uppercase tracking-wider mb-3'>System Status</h3>
      <div className='flex items-center gap-2'>
        <div className='flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500 shrink-0'>
          <Shield className='h-3 w-3' />
        </div>
        <div className='flex-1'>
          <div className='text-xs font-semibold text-fd-foreground'>RAG Pipeline</div>
          <div className='text-[0.625rem] text-fd-muted-foreground'>All systems operational</div>
        </div>
      </div>
    </div>
  );
}

export function RagDashboard() {
  return (
    <div className='flex flex-col h-full gap-4'>
      <div className='flex items-center justify-between'>
        <div>
          <h2 className='text-lg font-semibold text-fd-foreground'>RAG Pipeline</h2>
          <p className='text-xs text-fd-muted-foreground mt-1'>
            Retrieval-Augmented Generation over your documents
          </p>
        </div>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            className='inline-flex h-8 items-center gap-2 rounded-md bg-emerald-600 px-3 text-xs font-semibold text-white transition-colors hover:bg-emerald-500'
          >
            <RefreshCw className='h-3 w-3' />
            <span>Refresh</span>
          </button>
        </div>
      </div>
      <div className='flex flex-col gap-4'>
        <div className='flex flex-col lg:flex-row gap-4'>
          <RagChatPanel className='flex-1' />
          <div className='flex flex-col gap-4 w-full lg:w-1/3'>
            <RagSystemStats />
            <RagDocumentUpload className='flex-1' />
          </div>
        </div>
      </div>
    </div>
  );
}
