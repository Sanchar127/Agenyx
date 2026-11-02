'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Bot,
  BrainCircuit,
  Cpu,
  FlaskConical,
  Sparkles,
  Telescope,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

import { usePlayground } from '@/features/playground/registry';

export function PlaygroundShell({ children }: { children: ReactNode }) {
  const { tools, activeToolId, setActiveToolId, tool } = usePlayground();

  const ActiveToolIcon = tool.icon;

  return (
    <div className='flex h-screen flex-col'>
      {/* Top bar */}
      <header className='flex h-14 shrink-0 items-center justify-between gap-4 border-b border-fd-border bg-fd-background px-4 sm:px-6'>
        <div className='flex min-w-0 items-center gap-3'>
          <Link
            href='/'
            className='inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-fd-muted-foreground transition-colors hover:bg-fd-muted hover:text-fd-foreground'
            aria-label='Back to home'
          >
            <ArrowLeft className='h-4 w-4' />
          </Link>
          <div className='flex items-center gap-2'>
            <span className='flex h-6 w-6 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500'>
              <ActiveToolIcon className='h-3.5 w-3.5' />
            </span>
            <span className='text-sm font-semibold text-fd-foreground'>
              Playground
            </span>
          </div>
        </div>

        <div className='flex items-center gap-2'>
          <Link
            href='/docs'
            className='inline-flex h-8 items-center justify-center rounded-md px-3 text-xs font-medium text-fd-muted-foreground transition-colors hover:bg-fd-muted hover:text-fd-foreground'
          >
            Documentation
          </Link>
        </div>
      </header>

      <div className='flex min-h-0 flex-1 overflow-hidden'>
        {/* Tool sidebar */}
        <aside className='w-full shrink-0 border-b border-fd-border bg-fd-background md:w-60 md:border-b-0 md:border-r'>
          <div className='flex gap-2 overflow-x-auto px-3 py-3 md:flex-col md:overflow-visible md:px-3 md:py-3'>
            {tools.map((tool) => {
              const Icon = tool.icon;
              const isActive = tool.id === activeToolId;

              return (
                <button
                  key={tool.id}
                  type='button'
                  onClick={() => setActiveToolId(tool.id)}
                  className={`inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors md:w-full ${
                    isActive
                      ? 'bg-fd-muted text-fd-accent-foreground'
                      : 'text-fd-muted-foreground hover:bg-fd-muted hover:text-fd-accent-foreground'
                  }`}
                >
                  <Icon className='h-4 w-4 shrink-0' />
                  <span className='truncate'>{tool.name}</span>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Main workspace */}
        <main id='playground-main' className='min-h-0 flex-1 overflow-hidden'>
          {children}
        </main>
      </div>
    </div>
  );
}
