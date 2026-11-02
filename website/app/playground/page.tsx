'use client';

import { usePlayground } from '@/features/playground/registry';

export default function PlaygroundPage() {
  const { tool, renderTool } = usePlayground();

  return <div className='h-full'>{renderTool()}</div>;
}
