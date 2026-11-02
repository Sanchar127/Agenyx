import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export function Cta() {
  return (
    <section className='border-t border-fd-border bg-fd-muted/40'>
      <div className='mx-auto max-w-6xl px-4 py-20 text-center sm:px-6 sm:py-24'>
        <h2 className='text-3xl font-bold tracking-tight text-fd-foreground sm:text-4xl'>
          Ready to run your first agent?
        </h2>
        <p className='mx-auto mt-4 max-w-2xl text-fd-muted-foreground'>
          Spin up the full Agenyx runtime locally or point the Playground at
          your own deployment and start orchestrating.
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
            href='/docs'
            className='inline-flex h-11 items-center justify-center rounded-md border border-fd-border bg-fd-card px-6 text-sm font-semibold text-fd-foreground transition-colors hover:bg-fd-muted'
          >
            Read the docs
          </Link>
        </div>
      </div>
    </section>
  );
}
