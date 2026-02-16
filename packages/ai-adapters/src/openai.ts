import OpenAI from 'openai';
import type {
  AIProvider,
  AIProviderConfig,
  ChatMessage,
  CompletionOptions,
  CompletionResult,
  StreamChunk,
} from './base';

export class OpenAIProvider implements AIProvider {
  readonly name = 'openai';
  readonly models: string[];

  private client: OpenAI;
  private defaultModel: string;

  constructor(config: AIProviderConfig) {
    this.client = new OpenAI({
      apiKey: config.apiKey,
      baseURL: config.baseUrl,
    });
    this.models = config.models;
    this.defaultModel = config.defaultModel || 'gpt-4o';
  }

  async complete(
    messages: ChatMessage[],
    options?: CompletionOptions
  ): Promise<CompletionResult> {
    const model = options?.model || this.defaultModel;

    const response = await this.client.chat.completions.create({
      model,
      messages: messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      temperature: options?.temperature,
      max_tokens: options?.maxTokens,
      top_p: options?.topP,
      stop: options?.stop,
    });

    const choice = response.choices[0];

    return {
      content: choice.message.content || '',
      model: response.model,
      inputTokens: response.usage?.prompt_tokens || 0,
      outputTokens: response.usage?.completion_tokens || 0,
      finishReason: choice.finish_reason || 'stop',
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

    const stream = await this.client.chat.completions.create({
      model,
      messages: messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      temperature: options?.temperature,
      max_tokens: options?.maxTokens,
      top_p: options?.topP,
      stop: options?.stop,
      stream: true,
      stream_options: { include_usage: true },
    });

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta;

      if (delta?.content) {
        content += delta.content;
        onChunk({
          content: delta.content,
          done: false,
        });
      }

      if (chunk.usage) {
        inputTokens = chunk.usage.prompt_tokens;
        outputTokens = chunk.usage.completion_tokens;
      }
    }

    onChunk({
      content: '',
      done: true,
      inputTokens,
      outputTokens,
    });

    return {
      content,
      model,
      inputTokens,
      outputTokens,
      finishReason: 'stop',
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      await this.client.models.list();
      return true;
    } catch {
      return false;
    }
  }
}
