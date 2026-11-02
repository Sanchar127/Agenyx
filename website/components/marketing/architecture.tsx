import { Fragment } from 'react';
import { ArrowRight, Brain, Boxes, Server, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface FlowNode {
  icon: LucideIcon;
  title: string;
  description: string;
}

const FLOW_NODES: FlowNode[] = [
  {
    icon: Server,
    title: 'Gateway',
    description:
      'Auth, rate limiting, and permission enforcement for every execution request.',
  },
  {
    icon: Boxes,
    title: 'Agent Runtime',
    description:
      'Plan, infer, execute tools, observe results, and decide the next step.',
  },
  {
    icon: Brain,
    title: 'Semantic Router',
    description:
      'Selects the best model and provider for each intent, with failover.',
  },
  {
    icon: Workflow,
    title: 'Inference + Sandbox',
    description:
      'LLM completion with tool-calling, executed inside isolated sandboxes.',
  },
];

export function Architecture() {
  return (
    <section id='architecture' className='border-t border-fd-border bg-fd-background'>
      <div className='mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24'>
        <div className='mx-auto max-w-2xl text-center'>
          <p className='text-sm font-semibold uppercase tracking-wider text-emerald-500'>
            Architecture
          </p>
          <h2 className='mt-3 text-3xl font-bold tracking-tight text-fd-foreground sm:text-4xl'>
            From intent to answer
          </h2>
          <p className='mt-4 text-fd-muted-foreground'>
            A single request flows through a tightly scoped runtime —
            from submission to final answer.
          </p>
        </div>

        <div className='mt-14 overflow-x-auto pb-2'>
          <ol className='flex min-w-max items-center gap-4'>
            {FLOW_NODES.map((node, index) => (
              <Fragment key={node.title}>
                {index > 0 ? (
                  <li
                    aria-hidden='true'
                    className='flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-fd-border bg-fd-card text-fd-muted-foreground'
                  >
                    <ArrowRight className='h-4 w-4' />
                  </li>
                ) : null}
                <li className='w-64 shrink-0 rounded-xl border border-fd-border bg-fd-card p-6'>
                  <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/20'>
                    <node.icon className='h-5 w-5' />
                  </div>
                  <h3 className='mt-4 text-base font-semibold text-fd-foreground'>
                    {node.title}
                  </h3>
                  <p className='mt-2 text-sm leading-relaxed text-fd-muted-foreground'>
                    {node.description}
                  </p>
                </li>
              </Fragment>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
