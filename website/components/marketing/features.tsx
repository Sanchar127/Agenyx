import { Activity, Brain, Code2, Database, ShieldCheck, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface Feature {
  icon: LucideIcon;
  title: string;
  description: string;
}

const FEATURES: Feature[] = [
  {
    icon: Brain,
    title: 'Semantic Routing',
    description:
      'Agenyx routes each intent to the best-suited model and provider automatically, with capability-aware fallback and failover.',
  },
  {
    icon: Workflow,
    title: 'Agent Orchestration',
    description:
      'Planner-driven execution loops that break goals into steps, call tools, observe results, and decide the next action.',
  },
  {
    icon: ShieldCheck,
    title: 'Sandboxed Tool Execution',
    description:
      'Tool calls run inside isolated sandboxes with filesystem, network, and resource limits enforced per execution.',
  },
  {
    icon: Database,
    title: 'Durable Task Queue',
    description:
      'Agent executions flow through a durable task queue with retries, exponential backoff, and dead-letter handling.',
  },
  {
    icon: Activity,
    title: 'Live Execution Events',
    description:
      'Execution lifecycle events stream in real time, giving you full visibility into long-running agent workflows.',
  },
  {
    icon: Code2,
    title: 'OpenAI-Compatible API',
    description:
      'A drop-in /v1/chat/completions endpoint with tool-calling support — bring your own client or use the Playground.',
  },
];

export function Features() {
  return (
    <section id='features' className='border-t border-fd-border bg-fd-muted/40'>
      <div className='mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24'>
        <div className='mx-auto max-w-2xl text-center'>
          <p className='text-sm font-semibold uppercase tracking-wider text-emerald-500'>
            Capabilities
          </p>
          <h2 className='mt-3 text-3xl font-bold tracking-tight text-fd-foreground sm:text-4xl'>
            An opinionated runtime for agents
          </h2>
          <p className='mt-4 text-fd-muted-foreground'>
            Everything required to move an AI agent from a prompt to a
            production execution, without rebuilding infrastructure.
          </p>
        </div>

        <div className='mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3'>
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className='rounded-xl border border-fd-border bg-fd-card p-6'
            >
              <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/20'>
                <feature.icon className='h-5 w-5' />
              </div>
              <h3 className='mt-4 text-base font-semibold text-fd-foreground'>
                {feature.title}
              </h3>
              <p className='mt-2 text-sm leading-relaxed text-fd-muted-foreground'>
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
