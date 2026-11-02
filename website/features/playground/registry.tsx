'use client';

import { useSyncExternalStore } from 'react';
import type { ComponentType, ReactNode } from 'react';
import {
  BrainCircuit,
  Bot,
  Cpu,
  FlaskConical,
  Sparkles,
  Telescope,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

import { ChatTool } from './tools/chat-tool';
import { ComingSoon } from './coming-soon';

export interface PlaygroundToolDefinition {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  component?: ComponentType;
}

const CHAT_TOOL: PlaygroundToolDefinition = {
  id: 'chat',
  name: 'Chat',
  description: 'Chat with an Agenyx agent',
  icon: Bot,
  component: ChatTool,
};

const FUTURE_TOOLS: PlaygroundToolDefinition[] = [
  {
    id: 'agent-builder',
    name: 'Agent Builder',
    description: 'Design and assemble agents visually',
    icon: BrainCircuit,
  },
  {
    id: 'prompt-playground',
    name: 'Prompt Playground',
    description: 'Iterate on prompts with evals',
    icon: Sparkles,
  },
  {
    id: 'model-playground',
    name: 'Model Playground',
    description: 'Compare model behaviour side by side',
    icon: Cpu,
  },
  {
    id: 'workflow-builder',
    name: 'Workflow Builder',
    description: 'Compose multi-agent workflows',
    icon: Workflow,
  },
  {
    id: 'evaluations',
    name: 'Evaluations',
    description: 'Evaluate agent trajectories',
    icon: FlaskConical,
  },
];

export const playgroundTools: PlaygroundToolDefinition[] =
  [CHAT_TOOL, ...FUTURE_TOOLS];

const toolMap = new Map<string, PlaygroundToolDefinition>(
  playgroundTools.map((tool) => [tool.id, tool]),
);

const DEFAULT_TOOL_ID = 'chat';

let activeToolId = DEFAULT_TOOL_ID;
const activeToolListeners = new Set<() => void>();

function subscribeActiveTool(listener: () => void) {
  activeToolListeners.add(listener);

  return () => {
    activeToolListeners.delete(listener);
  };
}

function getActiveToolId() {
  return activeToolId;
}

function getServerActiveToolId() {
  return DEFAULT_TOOL_ID;
}

function setActiveToolId(id: string) {
  if (id === activeToolId) return;

  activeToolId = id;
  activeToolListeners.forEach((listener) => listener());
}

export function useActiveToolId() {
  const id = useSyncExternalStore(
    subscribeActiveTool,
    getActiveToolId,
    getServerActiveToolId,
  );

  return id;
}

export function usePlayground() {
  const activeToolId = useActiveToolId();
  const tool = toolMap.get(activeToolId) ?? toolMap.get(DEFAULT_TOOL_ID)!;
  const ToolComponent = tool.component;

  const renderTool = (): ReactNode => {
    if (ToolComponent) {
      const ActiveTool = ToolComponent;
      return <ActiveTool />;
    }

    return (
      <ComingSoon
        icon={tool.icon}
        name={tool.name}
        description={tool.description}
      />
    );
  };

  return {
    tools: playgroundTools,
    activeToolId,
    setActiveToolId,
    tool,
    renderTool,
  };
}
