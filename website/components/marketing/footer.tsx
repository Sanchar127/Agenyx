import Link from 'next/link';
import { Bot } from 'lucide-react';

import { githubUrl } from '@/lib/shared';

export function Footer() {
  return (
    <footer className='border-t border-fd-border bg-fd-background'>
      <div className='mx-auto max-w-6xl px-4 py-14 sm:px-6'>
        <div className='grid gap-10 md:grid-cols-3'>
          <div className='md:col-span-1'>
            <div className='flex items-center gap-2.5'>
              <span className='flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/30'>
                <Bot className='h-4 w-4' />
              </span>
              <span className='text-base font-semibold tracking-tight text-fd-foreground'>
                Agenyx
              </span>
            </div>
            <p className='mt-4 max-w-xs text-sm leading-relaxed text-fd-muted-foreground'>
              The runtime for building, deploying, and running AI agents.
            </p>
          </div>

          <div>
            <h3 className='text-sm font-semibold text-fd-foreground'>
              Product
            </h3>
            <ul className='mt-4 flex flex-col gap-2'>
              <li>
                <Link
                  href='/playground'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  Playground
                </Link>
              </li>
              <li>
                <Link
                  href='/docs'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  Documentation
                </Link>
              </li>
              <li>
                <a
                  href={githubUrl}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  GitHub
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h3 className='text-sm font-semibold text-fd-foreground'>
              Resources
            </h3>
            <ul className='mt-4 flex flex-col gap-2'>
              <li>
                <a
                  href={githubUrl}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  GitHub Repository
                </a>
              </li>
              <li>
                <Link
                  href='/docs'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  Documentation
                </Link>
              </li>
              <li>
                <Link
                  href='/playground'
                  className='text-sm text-fd-muted-foreground transition-colors hover:text-fd-foreground'
                >
                  AI Playground
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className='mt-12 flex flex-col items-start justify-between gap-4 border-t border-fd-border pt-8 sm:flex-row sm:items-center'>
          <p className='text-sm text-fd-muted-foreground'>
            © {new Date().getFullYear()} Agenyx. All rights reserved.
          </p>
          <p className='text-sm text-fd-muted-foreground'>
            Built for developers who ship AI agents.
          </p>
        </div>
      </div>
    </footer>
  );
}
