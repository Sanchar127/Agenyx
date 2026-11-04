'use client';

import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

type PreProps = React.DetailedHTMLProps<
  React.HTMLAttributes<HTMLPreElement>,
  HTMLPreElement
>;

export function MermaidPre({ children, ...props }: PreProps) {
  const childrenArray = React.Children.toArray(children);
  const codeEl = childrenArray.find(
    (c): c is React.ReactElement => React.isValidElement(c),
  );

  const isMermaid =
    !!codeEl &&
    codeEl.type === 'code' &&
    typeof (codeEl.props as Record<string, unknown>).className === 'string' &&
    String(
      (codeEl.props as Record<string, unknown>).className,
    ).includes('language-mermaid');

  if (isMermaid && codeEl) {
    const code = String(
      (codeEl.props as Record<string, unknown>).children,
    );
    return <MermaidDiagram code={code} />;
  }

  return <pre {...props}>{children}</pre>;
}

function MermaidDiagram({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current) return;

    const render = async () => {
      try {
        const { svg } = await mermaid.render(
          `mermaid-${Math.random().toString(36).slice(2)}`,
          code,
        );
        setSvg(svg);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setSvg(null);
      }
    };

    render();
  }, [code]);

  if (error) {
    return (
      <div className='rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive'>
        <p className='font-medium'>Mermaid render error</p>
        <pre className='mt-2 overflow-x-auto whitespace-pre-wrap break-all text-xs'>
          {error}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className='h-12 w-full animate-pulse rounded-md bg-muted'></div>
    );
  }

  return (
    <div
      ref={ref}
      className='mermaid-diagram overflow-x-auto my-6'
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
