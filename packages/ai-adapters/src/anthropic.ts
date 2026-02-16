import Anthropic from '@anthropic-ai/sdk';
import type {
  AIProvider,
  AIProviderConfig,
  ChatMessage,
  CompletionOptions,
  CompletionResult,
  StreamChunk,
} from './base';

export class AnthropicProvider implements AIProvider {
  readonly name = 'anthropic';
  readonly models: string[];

  private client: Anthropic;
  private defaultModel: string;

  constructor(config: AIProviderConfig) {
    this.client = new Anthropic({
      apiKey: config.apiKey,
      baseURL: config.baseUrl,
    });
    this.models = config.models;
    this.defaultModel = config.defaultModel || 'claude-sonnet-4-20250514';
  }

  async complete(
    messages: ChatMessage[],
    options?: CompletionOptions
  ): Promise<CompletionResult> {
    const model = options?.model || this.defaultModel;

    // Extract system message
    const systemMessage = messages.find((m) => m.role === 'system');
    const conversationMessages = messages.filter((m) => m.role !== 'system');

    const response = await this.client.messages.create({
      model,
      max_tokens: options?.maxTokens || 4096,
      system: systemMessage?.content,
      messages: conversationMessages.map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      })),
    });

    const textBlock = response.content.find(
      (block): block is Anthropic.TextBlock => block.type === 'text'
    );

    return {
      content: textBlock?.text || '',
      model: response.model,
      inputTokens: response.usage.input_tokens,
      outputTokens: response.usage.output_tokens,
      finishReason: response.stop_reason || 'end_turn',
    };
  }

  async completeStream(
    messages: ChatMessage[],
    onChunk: (chunk: StreamChunk) => void,
    options?: CompletionOptions
  ): Promise<CompletionResult> {
    const model = options?.model || this.defaultModel;
    let content = '';
    let inputTokens = 0;
    let outputTokens = 0;

    // Extract system message
    const systemMessage = messages.find((m) => m.role === 'system');
    const conversationMessages = messages.filter((m) => m.role !== 'system');

    const stream = this.client.messages.stream({
      model,
      max_tokens: options?.maxTokens || 4096,
      system: systemMessage?.content,
      messages: conversationMessages.map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      })),
    });

    stream.on('text', (text) => {
      content += text;
      onChunk({
        content: text,
        done: false,
      });
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    stream.on('messageStart' as any, (event: { message: { usage: { input_tokens: number } } }) => {
      inputTokens = event.message.usage.input_tokens;
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    stream.on('messageDelta' as any, (event: { usage?: { output_tokens: number } }) => {
      outputTokens = event.usage?.output_tokens || outputTokens;
    });

    const response = await stream.finalMessage();

    onChunk({
      content: '',
      done: true,
      inputTokens: response.usage.input_tokens,
      outputTokens: response.usage.output_tokens,
    });

    const textBlock = response.content.find(
      (block: Anthropic.ContentBlock): block is Anthropic.TextBlock => block.type === 'text'
    );

    return {
      content: textBlock?.text || content,
      model: response.model,
      inputTokens: response.usage.input_tokens,
      outputTokens: response.usage.output_tokens,
      finishReason: response.stop_reason || 'end_turn',
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      // Simple check by listing models (if available) or just verify API key exists
      return !!this.client;
    } catch {
      return false;
    }
  }
}
