'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { Bot, Check, Copy, Send } from 'lucide-react';

import { agentApi, ApiError, type AgentExecutionState } from '@/lib/api/client';

const CONVERSATIONS_STORAGE_KEY = 'agenyx:playground:conversations';
const POLL_INTERVAL_MS = 2000;
const MAX_EXECUTION_WAIT_MS = 15 * 60 * 1000;

export type ChatMessageStatus =
  | 'sending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  status: ChatMessageStatus;
  executionId?: string;
  error?: string;
}

export interface ChatConversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

function createConversation(): ChatConversation {
  return {
    id: crypto.randomUUID(),
    title: 'New conversation',
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

function loadConversations(): ChatConversation[] {
  if (typeof window === 'undefined') return [];

  try {
    const raw = window.localStorage.getItem(CONVERSATIONS_STORAGE_KEY);

    if (!raw) return [];

    const parsed: unknown = JSON.parse(raw);

    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (item): item is ChatConversation =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as ChatConversation).id === 'string' &&
        Array.isArray((item as ChatConversation).messages),
    );
  } catch {
    return [];
  }
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const details = error.details as
      | { detail?: unknown; error?: { message?: string } }
      | undefined;

    const detail =
      typeof details?.detail === 'string'
        ? details.detail
        : typeof details?.error?.message === 'string'
          ? details.error.message
          : undefined;

    if (detail) return detail;

    if (error.status === 401) {
      return 'Agenyx API key rejected the request. Check your API configuration.';
    }

    if (error.status === 404) {
      return 'Execution not found. It may have expired.';
    }

    if (error.status === 429) {
      return 'Rate limit exceeded. Please retry shortly.';
    }

    return `Agenyx API error (status ${error.status}).`;
  }

  if (error instanceof Error) return error.message;

  return 'Unexpected error contacting the Agenyx API.';
}

export function ChatTool() {
  const [conversations, setConversations] = useState<ChatConversation[]>(
    loadConversations,
  );
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(() => loadConversations()[0]?.id ?? null);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(
    null,
  );

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        CONVERSATIONS_STORAGE_KEY,
        JSON.stringify(conversations),
      );
    } catch {
      // Storage can be unavailable (private mode); chat still works in-memory.
    }
  }, [conversations]);

  const activeConversation =
    conversations.find(
      (conversation) => conversation.id === activeConversationId,
    ) ?? conversations[0];

  const messages = activeConversation?.messages ?? [];

  useEffect(() => {
    const element = scrollRef.current;

    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const element = textareaRef.current;

    if (!element) return;

    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [input]);

  const updateConversation = useCallback(
    (
      conversationId: string,
      updater: (conversation: ChatConversation) => ChatConversation,
    ) => {
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? updater(conversation)
            : conversation,
        ),
      );
    },
    [],
  );

  const runExecution = useCallback(
    async (
      intent: string,
    ): Promise<{
      executionId: string;
      answer?: string;
      error?: string;
    }> => {
      const { execution_id: executionId } = await agentApi.createExecution(
        intent,
      );
      const startedAt = Date.now();

      const poll = async (): Promise<{
        answer?: string;
        error?: string;
      }> => {
        const state: AgentExecutionState = await agentApi.getExecution(
          executionId,
        );

        const status = state.status;

        if (status === 'completed') {
          return { answer: state.answer };
        }

        if (status === 'failed') {
          return {
            error: state.error ?? 'The agent execution failed.',
          };
        }

        if (status === 'cancelled') {
          return { error: 'The agent execution was cancelled.' };
        }

        if (Date.now() - startedAt > MAX_EXECUTION_WAIT_MS) {
          return { error: 'The agent execution timed out.' };
        }

        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

        return poll();
      };

      const outcome = await poll();

      return {
        executionId,
        answer: outcome.answer,
        error: outcome.error,
      };
    },
    [],
  );

  const sendMessage = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();

      if (!text || isRunning || !activeConversation) return;

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        createdAt: Date.now(),
        status: 'completed',
      };

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        createdAt: Date.now(),
        status: 'running',
      };

      const conversationId = activeConversation.id;

      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        title:
          conversation.messages.length === 0
            ? text.slice(0, 40)
            : conversation.title,
        updatedAt: Date.now(),
        messages: [...conversation.messages, userMessage, assistantMessage],
      }));

      setIsRunning(true);

      try {
        const { executionId, answer, error } = await runExecution(text);

        updateConversation(conversationId, (conversation) => ({
          ...conversation,
          messages: conversation.messages.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  status: error ? 'failed' : 'completed',
                  content: answer ?? '',
                  error,
                  executionId,
                }
              : message,
          ),
        }));
      } catch (error) {
        updateConversation(conversationId, (conversation) => ({
          ...conversation,
          messages: conversation.messages.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  status: 'failed',
                  error: toErrorMessage(error),
                }
              : message,
          ),
        }));
      } finally {
        setIsRunning(false);
      }
    },
    [activeConversation, isRunning, runExecution, updateConversation],
  );

  const handleNewConversation = useCallback(() => {
    const conversation = createConversation();

    setConversations((current) => [conversation, ...current]);
    setActiveConversationId(conversation.id);
  }, []);

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      setActiveConversationId(conversationId);
    },
    [],
  );

  const handleClearConversation = useCallback(() => {
    if (!activeConversation) return;

    updateConversation(activeConversation.id, (conversation) => ({
      ...conversation,
      messages: [],
      updatedAt: Date.now(),
    }));
  }, [activeConversation, updateConversation]);

  const handleRetry = useCallback(() => {
    if (!activeConversation) return;

    const lastUserMessage = [...activeConversation.messages]
      .reverse()
      .find((message) => message.role === 'user');

    if (lastUserMessage) {
      void sendMessage(lastUserMessage.content);
    }
  }, [activeConversation, sendMessage]);

  const handleCopy = useCallback(async (message: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);

      setTimeout(() => {
        setCopiedMessageId((current) => (current === message.id ? null : current));
      }, 2000);
    } catch {
      // Clipboard access can be denied; ignore copy failures.
    }
  }, []);

  const handleSubmit = useCallback(() => {
    void sendMessage(input);
    setInput('');
  }, [input, sendMessage]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const isThinking =
    isRunning ||
    messages.some(
      (message) =>
        message.status === 'running' || message.status === 'sending',
    );

  return (
    <div className='flex h-full flex-col'>
      {/* Conversation header */}
      <div className='flex items-center justify-between gap-3 border-b border-fd-border px-4 py-3'>
        <div className='min-w-0'>
          <h2 className='truncate text-sm font-semibold text-fd-foreground'>
            {activeConversation?.title ?? 'Chat'}
          </h2>
          <p className='text-xs text-fd-muted-foreground'>
            {isThinking ? 'Agenyx is working on your request…' : 'Ask an Agenyx agent anything.'}
          </p>
        </div>

        <div className='flex shrink-0 items-center gap-2'>
          <button
            type='button'
            onClick={handleNewConversation}
            className='inline-flex h-8 items-center justify-center rounded-md border border-fd-border px-3 text-xs font-medium text-fd-foreground transition-colors hover:bg-fd-muted'
          >
            New conversation
          </button>
          <button
            type='button'
            onClick={handleClearConversation}
            disabled={messages.length === 0}
            className='inline-flex h-8 items-center justify-center rounded-md border border-fd-border px-3 text-xs font-medium text-fd-muted-foreground transition-colors hover:bg-fd-muted disabled:cursor-not-allowed disabled:opacity-50'
          >
            Clear
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className='flex-1 overflow-y-auto px-4 py-6'>
        {messages.length > 0 && conversations.length > 1 ? (
          <div className='mx-auto mb-6 flex max-w-3xl gap-2 overflow-x-auto pb-2'>
            {conversations.map((conversation) => {
              const isActive =
                conversation.id === (activeConversation?.id ?? '');

              return (
                <button
                  key={conversation.id}
                  type='button'
                  onClick={() => handleSelectConversation(conversation.id)}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                      : 'border-fd-border bg-fd-card text-fd-muted-foreground hover:bg-fd-muted hover:text-fd-accent-foreground'
                  }`}
                >
                  {conversation.title}
                </button>
              );
            })}
          </div>
        ) : null}

        {messages.length === 0 ? (
          <div className='flex h-full min-h-64 flex-col items-center justify-center text-center'>
            <div className='flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/20'>
              <Bot className='h-7 w-7' />
            </div>
            <h3 className='mt-6 text-base font-semibold text-fd-foreground'>
              How can I help you build?
            </h3>
            <p className='mt-2 max-w-md text-sm text-fd-muted-foreground'>
              Ask an Agenyx agent to research, plan, or execute a task. Answers
              arrive once the agent completes its run.
            </p>
          </div>
        ) : (
          <div className='mx-auto flex w-full max-w-3xl flex-col gap-6'>
            {messages.map((message) => (
              <div
                key={message.id}
                className={message.role === 'user' ? 'flex justify-end' : 'flex gap-3'}
              >
                {message.role === 'assistant' ? (
                  <div className='mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-inset ring-emerald-500/20'>
                    <Bot className='h-4 w-4' />
                  </div>
                ) : null}

                <div
                  className={
                    message.role === 'user'
                      ? 'max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-600/15 px-4 py-2.5 text-sm text-fd-foreground ring-1 ring-inset ring-emerald-500/20'
                      : 'min-w-0 flex-1'
                  }
                >
                  {message.role === 'user' ? (
                    <p className='whitespace-pre-wrap text-sm text-fd-foreground'>
                      {message.content}
                    </p>
                  ) : (
                    <div className='space-y-2'>
                      {message.status === 'running' || message.status === 'sending' ? (
                        <div className='flex items-center gap-2 text-sm text-fd-muted-foreground'>
                          <span className='h-2 w-2 animate-pulse rounded-full bg-emerald-500' />
                          Agenyx is working…
                        </div>
                      ) : null}

                      {message.content ? (
                        <p className='whitespace-pre-wrap text-sm leading-relaxed text-fd-foreground'>
                          {message.content}
                        </p>
                      ) : null}

                      {message.status === 'failed' && message.error ? (
                        <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400'>
                          {message.error}
                          <button
                            type='button'
                            onClick={handleRetry}
                            className='mt-2 inline-flex h-7 items-center rounded-md border border-red-500/40 px-2.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/10'
                          >
                            Retry
                          </button>
                        </div>
                      ) : null}

                      {message.status === 'completed' && message.content ? (
                        <div className='flex items-center justify-end pt-1'>
                          <button
                            type='button'
                            onClick={() => void handleCopy(message)}
                            className='inline-flex h-7 w-7 items-center justify-center rounded-md text-fd-muted-foreground transition-colors hover:bg-fd-muted hover:text-fd-foreground'
                            aria-label='Copy message'
                          >
                            {copiedMessageId === message.id ? (
                              <Check className='h-3.5 w-3.5 text-emerald-500' />
                            ) : (
                              <Copy className='h-3.5 w-3.5' />
                            )}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className='border-t border-fd-border p-4'>
        <div className='mx-auto max-w-3xl'>
          <div className='rounded-xl border border-fd-border bg-fd-card'>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='Ask an Agenyx agent anything…'
              rows={1}
              disabled={isRunning}
              className='max-h-[200px] w-full resize-none bg-transparent px-4 pb-2 pt-3 text-sm text-fd-foreground placeholder:text-fd-muted-foreground focus:outline-none disabled:opacity-60'
            />
            <div className='flex items-center justify-between border-t border-fd-border/60 px-3 pt-2 pb-2'>
              <p className='text-xs text-fd-muted-foreground'>
                Enter to send · Shift + Enter for a new line
              </p>
              <button
                type='button'
                onClick={handleSubmit}
                disabled={!input.trim() || isRunning}
                className='inline-flex h-8 items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-3 text-xs font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50'
              >
                Send
                <Send className='h-3.5 w-3.5' />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
