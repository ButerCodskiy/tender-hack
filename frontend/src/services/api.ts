import { Citation } from '../types/chat';
import { clearStoredAuth, getStoredTokens } from './auth';
import { isStandaloneMode } from '../config/mode';
import {
  simulateMockChatStream,
  getMockChatState,
  mockEscalateTicket,
  mockResolveTicket,
  mockSubmitFeedback,
} from './mockData';

interface SendMessagePayload {
  chatId?: string;
  ticketId?: string;
  newTicket?: boolean;
  content: string;
  category?: string;
  model?: string;
}

export interface StreamCallbacks {
  onStatus?: (status: string) => void;
  onSources?: (citations: Citation[]) => void;
  onChunk?: (chunk: string) => void;
  onDone?: (fullText: string, messageId?: string, ticketId?: string) => void;
  onSessionTerminated?: (reason: string, message: string) => void;
  onError?: (err: Error) => void;
}

export interface ActiveTicketSummary {
  id: string;
  status: string;
  priority: string;
  line_code?: string | null;
  assigned_operator_name?: string | null;
  created_at: string;
}

export interface ClientResolveTicketResponse {
  status: string;
  ticket_id: string;
  closed_at: string;
}

export interface BackendChatState {
  chat_id: string;
  active_ticket: ActiveTicketSummary | null;
  messages: Array<{
    id: string;
    ticket_id: string;
    sender_type: 'client' | 'bot' | 'operator' | 'system';
    text: string;
    created_at: string;
    sources?: Array<{
      chunk_id: string;
      doc_id: string;
      quote_text?: string;
    }>;
  }>;
  can_escalate?: boolean;
  can_cancel?: boolean;
  can_feedback?: boolean;
  feedback_ticket_id?: string | null;
}

export async function fetchChatState(): Promise<BackendChatState | null> {
  if (isStandaloneMode()) {
    return getMockChatState();
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) return null;

  try {
    const res = await fetch('/api/v1/chat', {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
      },
    });

    if (!res.ok) {
      if (res.status === 401) {
        clearStoredAuth();
      }
      return null;
    }

    return await res.json();
  } catch (err) {
    console.error('Ошибка получения состояния чата:', err);
    return null;
  }
}

export async function streamChatMessage(
  payload: SendMessagePayload,
  callbacks: StreamCallbacks
): Promise<void> {
  if (isStandaloneMode()) {
    return simulateMockChatStream(payload.content, callbacks);
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    clearStoredAuth();
    const authErr = new Error('Для отправки сообщений необходимо войти в систему.');
    callbacks.onError?.(authErr);
    throw authErr;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 45000);

  try {
    const res = await fetch('/api/v1/chat/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream, application/json',
        'Authorization': `Bearer ${tokens.access_token}`,
      },
      body: JSON.stringify({
        text: payload.content.trim(),
        ticket_id: payload.ticketId || undefined,
        new_ticket: payload.newTicket || false,
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      if (res.status === 401) {
        clearStoredAuth();
        const err = new Error('Сессия истекла. Пожалуйста, выполните вход заново.');
        callbacks.onError?.(err);
        throw err;
      }

      let errMessage = `Ошибка сервера (${res.status})`;
      try {
        const errData = await res.json();
        if (errData?.detail) {
          errMessage =
            typeof errData.detail === 'string'
              ? errData.detail
              : errData.detail.message || JSON.stringify(errData.detail);
        }
      } catch {
        // ignore parse error
      }

      const serverErr = new Error(errMessage);
      callbacks.onError?.(serverErr);
      throw serverErr;
    }

    if (res.body) {
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('text/event-stream')) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let currentEvent = '';
        let accumulatedText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line) {
              currentEvent = '';
              continue;
            }
            if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim();
              continue;
            }
            if (line.startsWith('data:')) {
              const dataStr = line.slice(5).trim();
              try {
                const data = JSON.parse(dataStr);
                if (currentEvent === 'status') {
                  const statusText =
                    data.message ||
                    (data.code === 'searching'
                      ? 'Идет поиск по нормативным регламентам...'
                      : data.code === 'reranking'
                      ? 'Анализ точности найденных статей...'
                      : data.code === 'classifying'
                      ? 'Определение тематики обращения...'
                      : 'Формирование ответа...');
                  callbacks.onStatus?.(statusText);
                } else if (currentEvent === 'sources') {
                  if (data.sources && Array.isArray(data.sources)) {
                    const citations: Citation[] = data.sources.map(
                      (src: {
                        chunk_id?: string;
                        doc_id?: string;
                        title?: string;
                        section_path?: string;
                        quote_text?: string;
                      }, idx: number) => ({
                        id: src.chunk_id || `src-${idx}`,
                        title: src.title || src.doc_id || 'Регламент Портала',
                        sectionPath: src.section_path || src.doc_id,
                        excerpt: src.quote_text,
                      })
                    );
                    callbacks.onSources?.(citations);
                  }
                } else if (currentEvent === 'sentence') {
                  const sentence = data.text || '';
                  if (sentence) {
                    accumulatedText += (accumulatedText.length > 0 ? ' ' : '') + sentence;
                    callbacks.onChunk?.(sentence);
                  }
                } else if (currentEvent === 'token') {
                  const token = data.token || '';
                  if (token) {
                    accumulatedText += token;
                    callbacks.onChunk?.(token);
                  }
                } else if (currentEvent === 'done') {
                  const text = data.text || accumulatedText;
                  callbacks.onDone?.(text, data.message_id, data.ticket_id);
                  return;
                } else if (currentEvent === 'degraded_mode') {
                  if (data.sources && Array.isArray(data.sources)) {
                    const citations: Citation[] = data.sources.map(
                      (
                        src: {
                          chunk_id?: string;
                          doc_id?: string;
                          title?: string;
                          section_path?: string;
                          quote_text?: string;
                        },
                        idx: number
                      ) => ({
                        id: src.chunk_id || `src-${idx}`,
                        title: src.title || src.doc_id || 'Регламент Портала',
                        sectionPath: src.section_path || src.doc_id,
                        excerpt: src.quote_text,
                      })
                    );
                    callbacks.onSources?.(citations);
                  }
                  const text =
                    data.message ||
                    'Информация по вашему запросу не найдена в нормативных регламентах.';
                  callbacks.onDone?.(text, data.message_id, data.ticket_id);
                  return;
                } else if (currentEvent === 'session_terminated') {
                  callbacks.onSessionTerminated?.(
                    data.reason || 'moderation',
                    data.message || 'Диалог закрыт модерацией'
                  );
                  return;
                }
              } catch (err) {
                console.warn('Failed to parse SSE JSON line:', line, err);
              }
            }
          }
        }

        if (accumulatedText) {
          callbacks.onDone?.(accumulatedText);
          return;
        }
      } else {
        // Fallback for direct JSON responses
        const data = await res.json();
        callbacks.onDone?.(data.content || data.reply || 'Ответ сформирован.', data.id, data.ticket_id);
        return;
      }
    }
  } catch (err: unknown) {
    const error =
      err instanceof Error
        ? err
        : new Error('Сбой сетевого подключения к серверу.');
    callbacks.onError?.(error);
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Ручной вызов оператора клиентом (эскалация диалога)
 */
export async function escalateTicket(
  reason?: string
): Promise<ActiveTicketSummary> {
  if (isStandaloneMode()) {
    return mockEscalateTicket();
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    throw new Error('Необходима авторизация');
  }

  const res = await fetch('/api/v1/chat/escalate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${tokens.access_token}`,
    },
    body: JSON.stringify({ reason: reason || 'client_requested' }),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const message =
      errData.detail?.message ||
      errData.detail ||
      'Ошибка при вызове оператора';
    throw new Error(message);
  }

  return await res.json();
}

/**
 * Подтверждение клиентом решения вопроса (кнопка «Вопрос решен»)
 */
export async function resolveTicket(
  ticketId: string
): Promise<ClientResolveTicketResponse> {
  if (isStandaloneMode()) {
    return mockResolveTicket(ticketId);
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    throw new Error('Необходима авторизация');
  }

  const res = await fetch(`/api/v1/chat/tickets/${ticketId}/resolve`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
    },
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const message =
      errData.detail?.message ||
      errData.detail ||
      'Ошибка при завершении обращения';
    throw new Error(message);
  }

  return await res.json();
}

/**
 * Отправка экспресс-оценки качества диалога (1–5 звезд и комментарий)
 */
export async function submitFeedback(
  ticketId: string,
  score: number,
  comment?: string
): Promise<void> {
  if (isStandaloneMode()) {
    return mockSubmitFeedback(ticketId, score, comment);
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    throw new Error('Необходима авторизация');
  }

  const res = await fetch(`/api/v1/chat/tickets/${ticketId}/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${tokens.access_token}`,
    },
    body: JSON.stringify({ score, comment: comment || undefined }),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const message =
      errData.detail?.message ||
      errData.detail ||
      'Ошибка при отправке отзыва';
    throw new Error(message);
  }
}

/**
 * Подписка на постоянный SSE-поток событий обращения клиента (GET /api/v1/chat/events)
 */
export function subscribeChatEvents(
  ticketId?: string,
  onEvent?: (event: string, data: any) => void
): () => void {
  if (isStandaloneMode()) {
    return () => {};
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    return () => {};
  }

  const controller = new AbortController();
  const url = ticketId
    ? `/api/v1/chat/events?ticket_id=${ticketId}&token=${tokens.access_token}`
    : `/api/v1/chat/events?token=${tokens.access_token}`;

  fetch(url, {
    signal: controller.signal,
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${tokens.access_token}`,
    },
  })
    .then(async (res) => {
      if (!res.ok || !res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const lines = part.split('\n');
          let currentEvent = 'message';
          let currentData = '';

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              currentData = line.replace('data:', '').trim();
            }
          }

          if (currentData) {
            try {
              const parsed = JSON.parse(currentData);
              onEvent?.(currentEvent, parsed);
            } catch {
              onEvent?.(currentEvent, currentData);
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        console.warn('SSE subscription error:', err);
      }
    });

  return () => {
    controller.abort();
  };
}
