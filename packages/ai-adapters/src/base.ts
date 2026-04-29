import type { OperationType } from '@musegraph/shared';

// AI Message types
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

// AI Completion options
export interface CompletionOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  stop?: string[];
  stream?: boolean;
}

// AI Completion result
export interface CompletionResult {
  content: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  finishReason: string;
}

// Streaming chunk
export interface StreamChunk {
  content: string;
  done: boolean;
  inputTokens?: number;
  outputTokens?: number;
}

// AI Provider interface
export interface AIProvider {
  readonly name: string;
  readonly models: string[];

  complete(
    messages: ChatMessage[],
    options?: CompletionOptions
  ): Promise<CompletionResult>;

  completeStream(
    messages: ChatMessage[],
    onChunk: (chunk: StreamChunk) => void,
    options?: CompletionOptions
  ): Promise<CompletionResult>;

  isAvailable(): Promise<boolean>;
}

// AI Provider config
export interface AIProviderConfig {
  apiKey: string;
  baseUrl?: string;
  defaultModel?: string;
  apiStyle?: 'responses' | 'chat_completions';
  models: string[];
}

// Text operation context
export interface TextOperationContext {
  projectId: string;
  userId: string;
  type: OperationType;
  input?: string;
  existingContent?: string;
  options?: Record<string, unknown>;
}

// Text operation result
export interface TextOperationResult {
  content: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

// Graph extraction result
export interface GraphExtractionResult {
  entities: Array<{
    name: string;
    type: string;
    properties?: Record<string, unknown>;
  }>;
  relations: Array<{
    source: string;
    target: string;
    type: string;
    properties?: Record<string, unknown>;
    weight?: number;
  }>;
}
