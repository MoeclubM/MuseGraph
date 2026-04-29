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
  private apiStyle: 'responses' | 'chat_completions';

  constructor(config: AIProviderConfig) {
    this.client = new OpenAI({
      apiKey: config.apiKey,
      baseURL: config.baseUrl,
    });
    this.models = config.models;
    this.defaultModel = config.defaultModel || 'gpt-4o';
    this.apiStyle = config.apiStyle === 'chat_completions' ? 'chat_completions' : 'responses';
  }

  async complete(
    messages: ChatMessage[],
    options?: CompletionOptions
  ): Promise<CompletionResult> {
    const model = options?.model || this.defaultModel;

    if (this.apiStyle === 'chat_completions') {
      const response = await this.client.chat.completions.create({
        model,
        messages: messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature: options?.temperature,
        max_tokens: options?.maxTokens,
        top_p: options?.topP,
      });

      return {
        content: response.choices[0]?.message?.content || '',
        model: response.model,
        inputTokens: response.usage?.prompt_tokens || 0,
        outputTokens: response.usage?.completion_tokens || 0,
        finishReason: response.choices[0]?.finish_reason || 'stop',
      };
    }

    const response = await this.client.responses.create({
      model,
      input: messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      temperature: options?.temperature,
      max_output_tokens: options?.maxTokens,
      top_p: options?.topP,
    });

    return {
      content: response.output_text || '',
      model: response.model,
      inputTokens: response.usage?.input_tokens || 0,
      outputTokens: response.usage?.output_tokens || 0,
      finishReason: 'stop',
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
    let responseModel = model;

    if (this.apiStyle === 'chat_completions') {
      const stream = await this.client.chat.completions.create({
        model,
        messages: messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature: options?.temperature,
        max_tokens: options?.maxTokens,
        top_p: options?.topP,
        stream: true,
        stream_options: { include_usage: true },
      });

      for await (const event of stream) {
        const choice = event.choices?.[0];
        const delta = choice?.delta?.content || '';
        if (delta) {
          content += delta;
          onChunk({
            content: delta,
            done: false,
          });
        }
        inputTokens = Math.max(inputTokens, event.usage?.prompt_tokens || 0);
        outputTokens = Math.max(outputTokens, event.usage?.completion_tokens || 0);
        if (event.model) {
          responseModel = event.model;
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
        model: responseModel,
        inputTokens,
        outputTokens,
        finishReason: 'stop',
      };
    }

    const stream = await this.client.responses.create({
      model,
      input: messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      temperature: options?.temperature,
      max_output_tokens: options?.maxTokens,
      top_p: options?.topP,
      stream: true,
    });

    for await (const event of stream) {
      if (event.type === 'response.output_text.delta') {
        content += event.delta;
        onChunk({
          content: event.delta,
          done: false,
        });
        continue;
      }
      if (event.type === 'response.completed') {
        inputTokens = event.response.usage?.input_tokens || 0;
        outputTokens = event.response.usage?.output_tokens || 0;
        responseModel = event.response.model || responseModel;
        continue;
      }
      if (event.type === 'response.failed') {
        throw new Error(event.response.error?.message || 'OpenAI response failed');
      }
      if (event.type === 'response.incomplete') {
        throw new Error('OpenAI response incomplete');
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
      model: responseModel,
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
