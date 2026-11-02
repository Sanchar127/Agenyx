import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export function Hero() {
  return (
    <section className='relative overflow-hidden'>
      <div
        aria-hidden='true'
        className='pointer-events-none absolute inset-x-0 top-0 -z-10 h-[620px] bg-[radial-gradient(ellipse_at_top,theme(--color-emerald-500/10%,transparent),transparent_65%)]'
      />
      <div className='relative mx-auto max-w-6xl px-4 pb-20 pt-20 text-center sm:px-6 sm:pt-28'>
        <Link
          href='/docs'
          className='inline-flex items-center gap-2 rounded-full border border-fd-border bg-fd-card px-3.5 py-1.5 text-xs font-medium text-fd-muted-foreground transition-colors hover:bg-fd-muted'
        >
          <span className='h-1.5 w-1.5 rounded-full bg-emerald-500' />
          Agenyx Runtime v0.1 — agent orchestration platform
        </Link>

        <h1 className='mt-6 text-4xl font-bold tracking-tight text-fd-foreground sm:text-5xl lg:text-6xl'>
          AI agents that{' '}
          <span className='bg-gradient-to-r from-emerald-400 via-emerald-500 to-teal-400 bg-clip-text text-transparent'>
            run to completion
          </span>
          .
        </h1>

        <p className='mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-fd-muted-foreground'>
          Agenyx is the orchestration runtime for autonomous AI agents.
          It plans, routes, executes tools in isolation, and keeps every
          execution durable — so agents ship with confidence.
        </p>

        <div className='mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row'>
          <Link
            href='/playground'
            className='inline-flex h-11 items-center justify-center gap-2 rounded-md bg-emerald-600 px-6 text-sm font-semibold text-white transition-colors hover:bg-emerald-500'
          >
            Open Playground
            <ArrowRight className='h-4 w-4' />
          </Link>
          <Link
            href='/signup'
            className='inline-flex h-11 items-center justify-center rounded-md border border-fd-border bg-fd-card px-6 text-sm font-semibold text-fd-foreground transition-colors hover:bg-fd-muted'
          >
            Get Started
          </Link>
        </div>

        <div className='mx-auto mt-14 max-w-2xl'>
          <div className='overflow-hidden rounded-xl border border-fd-border bg-zinc-950 text-left shadow-2xl shadow-black/20'>
            <div className='flex items-center gap-2 border-b border-white/10 px-4 py-2.5'>
              <span className='h-2.5 w-2.5 rounded-full bg-red-500/80' />
              <span className='h-2.5 w-2.5 rounded-full bg-yellow-500/80' />
              <span className='h-2.5 w-2.5 rounded-full bg-green-500/80' />
              <span className='ml-2 font-mono text-xs text-zinc-500'>
                agenyx — agent execution
              </span>
            </div>
            <pre className='overflow-x-auto px-4 py-4 font-mono text-xs leading-relaxed text-zinc-300 sm:text-sm'>
              <code>{`curl -X POST https://api.agenyx.dev/v1/agent/run \\
  -H "Authorization: Bearer $AGENYX_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"intent": "Research the latest agent frameworks and summarize the tradeoffs."}'

HTTP/1.1 202 Accepted
content-type: application/json

{
  "execution_id": "9b1f8a2e-7c4d-4f6a-9e3b-2d5f1a8c6b7e",
  "status": "queued"
}`}</code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
