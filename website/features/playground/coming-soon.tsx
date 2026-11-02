import { Telescope } from 'lucide-react';

import type { PlaygroundToolDefinition } from './registry';

interface ComingSoonProps {
  icon?: PlaygroundToolDefinition['icon'];
  name: string;
  description: string;
}

export function ComingSoon({ icon: Icon, name, description }: ComingSoonProps) {
  return (
    <div className='flex h-full flex-col items-center justify-center px-6 py-16 text-center'>
      <div className='flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/20'>
        {Icon ? <Icon className='h-7 w-7' /> : <Telescope className='h-7 w-7' />}
      </div>
      <h2 className='mt-6 text-xl font-semibold text-fd-foreground'>
        {name} is coming soon
      </h2>
      <p className='mt-2 max-w-md text-sm leading-relaxed text-fd-muted-foreground'>
        {description}. This capability is on the roadmap and will be
        available in an upcoming release.
      </p>
    </div>
  );
}
