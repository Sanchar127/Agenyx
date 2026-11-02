'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import type { ComponentProps } from 'react';
import { Bot, Menu, X } from 'lucide-react';

import { cn } from '@/lib/cn';
import { githubUrl } from '@/lib/shared';

const NAV_ITEMS = [
  { label: 'Features', href: '#features' },
  { label: 'Architecture', href: '#architecture' },
  { label: 'Docs', href: '/docs' },
  { label: 'Playground', href: '/playground' },
];

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox='0 0 24 24'
      fill='currentColor'
      className={className}
      aria-hidden='true'
    >
      <path d='M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12' />
    </svg>
  );
}

export function SiteHeader({ className }: ComponentProps<'header'>) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  const closeMobile = () => setMobileOpen(false);

  const navLinkClassName = (active: boolean) =>
    cn(
      'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
      active
        ? 'bg-fd-muted text-fd-accent-foreground'
        : 'text-fd-muted-foreground hover:bg-fd-muted hover:text-fd-accent-foreground',
    );

  const desktopNav = (
    <nav className='hidden items-center gap-1 md:flex'>
      {NAV_ITEMS.map((item) => {
        const active =
          item.href === '/docs'
            ? pathname === '/docs'
            : item.href === '/playground'
              ? pathname === '/playground'
              : false;

        return (
          <Link
            key={item.href}
            href={item.href}
            className={navLinkClassName(active)}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const mobileNav = (
    <nav className='flex flex-col gap-1 px-4 py-3 md:hidden'>
      {NAV_ITEMS.map((item) => {
        const active =
          item.href === '/docs'
            ? pathname === '/docs'
            : item.href === '/playground'
              ? pathname === '/playground'
              : false;

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={closeMobile}
            className={cn(
              'rounded-md px-3 py-2 text-sm font-medium',
              active
                ? 'bg-fd-muted text-fd-accent-foreground'
                : 'text-fd-muted-foreground',
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <header
      className={cn(
        'sticky top-0 z-40 w-full border-b border-fd-border bg-fd-background/80 backdrop-blur-md',
        className,
      )}
    >
      <div className='mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6'>
        <Link
          href='/'
          onClick={closeMobile}
          className='flex items-center gap-2.5'
        >
          <span className='flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/30'>
            <Bot className='h-4 w-4' />
          </span>
          <span className='text-base font-semibold tracking-tight text-fd-foreground'>
            Agenyx
          </span>
        </Link>

        {desktopNav}

        <div className='flex items-center gap-2'>
          <Link
            href={githubUrl}
            className='inline-flex h-9 w-9 items-center justify-center rounded-md text-fd-muted-foreground transition-colors hover:bg-fd-muted hover:text-fd-accent-foreground'
            aria-label='Agenyx on GitHub'
          >
            <GitHubMark className='h-4 w-4' />
          </Link>

          <Link
            href='/login'
            className='hidden h-9 items-center justify-center rounded-md px-4 text-sm font-medium text-fd-foreground transition-colors hover:bg-fd-muted sm:inline-flex'
          >
            Sign in
          </Link>

          <Link
            href='/signup'
            className='inline-flex h-9 items-center justify-center rounded-md bg-emerald-600 px-4 text-sm font-medium text-white transition-colors hover:bg-emerald-500'
          >
            Get Started
          </Link>

          <button
            type='button'
            className='inline-flex h-9 w-9 items-center justify-center rounded-md text-fd-muted-foreground transition-colors hover:bg-fd-muted hover:text-fd-accent-foreground md:hidden'
            onClick={() => setMobileOpen((open) => !open)}
            aria-label='Toggle navigation menu'
          >
            {mobileOpen ? (
              <X className='h-4 w-4' />
            ) : (
              <Menu className='h-4 w-4' />
            )}
          </button>
        </div>
      </div>

      {mobileOpen ? (
        <div className='border-t border-fd-border bg-fd-background md:hidden'>
          {mobileNav}
          <div className='flex flex-col gap-2 border-t border-fd-border px-4 py-3'>
            <Link
              href='/login'
              onClick={closeMobile}
              className='inline-flex h-10 items-center justify-center rounded-md border border-fd-border px-4 text-sm font-medium text-fd-foreground transition-colors hover:bg-fd-muted'
            >
              Sign in
            </Link>
            <Link
              href='/signup'
              onClick={closeMobile}
              className='inline-flex h-10 items-center justify-center rounded-md bg-emerald-600 px-4 text-sm font-medium text-white transition-colors hover:bg-emerald-500'
            >
              Get Started
            </Link>
          </div>
        </div>
      ) : null}
    </header>
  );
}
