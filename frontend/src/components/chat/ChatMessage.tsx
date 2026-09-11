import React, { useState } from 'react';
import {
  Sparkles,
  Copy,
  Check,
  Pencil,
  RotateCw,
  ThumbsUp,
  ThumbsDown,
  BookOpen,
  CheckCircle2,
  Headphones,
  AlertTriangle,
} from 'lucide-react';
import { Message } from '../../types/chat';

interface ChatMessageProps {
  message: Message;
  onEditMessage?: (id: string, newContent: string) => void;
  onRegenerate?: (id: string) => void;
  onResolveTicket?: () => void;
  onEscalateToOperator?: () => void;
  onFeedback?: (id: string, isPositive: boolean) => void;
  isEscalated?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  onEditMessage,
  onRegenerate,
  onResolveTicket,
  onEscalateToOperator,
  onFeedback,
  isEscalated = false,
}) => {
  const [isCopied, setIsCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [feedbackGiven, setFeedbackGiven] = useState<'positive' | 'negative' | null>(null);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (e) {
      console.error('Не удалось скопировать текст:', e);
    }
  };

  const handleSaveEdit = () => {
    if (onEditMessage && editContent.trim()) {
      onEditMessage(message.id, editContent);
      setIsEditing(false);
    }
  };

  // 1. Thinking / Loading State
  if (message.type === 'thinking') {
    return (
      <div className="flex flex-col space-y-3 py-4 animate-in fade-in duration-200">
        <div className="flex items-center gap-2">
          <div className="size-6 rounded-lg bg-primary-50 flex items-center justify-center text-primary-600">
            <Sparkles className="size-3.5" />
          </div>
          <span className="text-xs font-semibold text-text-100">
            ИИ-Ассистент Портала
          </span>
        </div>
        <div className="flex items-center gap-1.5 pl-8">
          <div className="size-2 rounded-full bg-primary-400 animate-bounce [animation-delay:-0.3s]" />
          <div className="size-2 rounded-full bg-primary-400 animate-bounce [animation-delay:-0.15s]" />
          <div className="size-2 rounded-full bg-primary-400 animate-bounce" />
          <span className="text-xs text-primary-700/80 font-medium ml-2 animate-pulse">
            {message.statusText || 'Поиск по базе регламентов...'}
          </span>
        </div>
      </div>
    );
  }

  // 2. System State
  if (message.type === 'system') {
    return (
      <div className="my-4 flex justify-center">
        <div className="max-w-xl px-4 py-2.5 rounded-2xl bg-amber-50 border border-amber-200/80 text-amber-900 text-xs md:text-sm flex items-start gap-2.5 shadow-xs">
          <AlertTriangle className="size-4.5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block mb-0.5">Системное уведомление</span>
            <p className="leading-relaxed">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // 3. User Message
  if (message.type === 'user') {
    return (
      <div className="flex justify-end py-3 group w-full min-w-0">
        <div className="w-full max-w-2xl flex flex-col items-end min-w-0">
          {isEditing ? (
            <div className="w-full bg-background-soft-100 rounded-3xl rounded-tr-md p-3 border border-gray-200">
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full bg-transparent text-sm md:text-base text-title-50 outline-none resize-none min-h-[80px] p-2"
              />
              <div className="flex justify-end gap-2 mt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsEditing(false);
                    setEditContent(message.content);
                  }}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg text-gray-600 hover:bg-gray-200 transition cursor-pointer"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition cursor-pointer shadow-xs"
                >
                  Сохранить
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="bg-background-soft-100 rounded-3xl rounded-tr-md px-5 py-3.5 text-title-50 text-sm md:text-base shadow-2xs max-w-full min-w-0 break-words">
                <p className="whitespace-pre-wrap leading-relaxed break-words [overflow-wrap:anywhere]">{message.content}</p>
              </div>

              {/* Action Buttons */}
              <div className="mt-1.5 flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
                <span className="text-[11px] text-gray-400 mr-1">{message.timestamp}</span>

                <button
                  type="button"
                  onClick={handleCopy}
                  title="Копировать"
                  className="size-7 rounded-full flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                >
                  {isCopied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                </button>

                {onEditMessage && (
                  <button
                    type="button"
                    onClick={() => setIsEditing(true)}
                    title="Редактировать вопрос"
                    className="size-7 rounded-full flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // 4. Assistant Message
  return (
    <div className="flex flex-col space-y-3 py-4 group w-full min-w-0">
      {/* Bot Header */}
      <div className="flex items-center gap-2">
        <div className="size-6 rounded-lg bg-gradient-to-tr from-primary-600 to-primary-400 flex items-center justify-center text-white shadow-2xs shrink-0">
          <Sparkles className="size-3.5" />
        </div>
        <span className="text-xs font-semibold text-title-50 truncate">
          ИИ-Ассистент Портала Поставщиков
        </span>
        <span className="text-[11px] text-gray-400 ml-auto shrink-0">{message.timestamp}</span>
      </div>

      {/* Message Content */}
      <div className="pl-8 text-title-50 text-sm md:text-base leading-relaxed space-y-3 min-w-0">
        <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {message.content}
          {message.isStreaming && (
            <span
              aria-hidden="true"
              className="inline-block w-1.5 h-4 ml-1 bg-primary-600 animate-pulse rounded-xs align-middle"
            />
          )}
        </div>

        {/* RAG Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-4 pt-3 border-t border-gray-100 space-y-2 animate-in fade-in duration-300">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-500">
              <BookOpen className="size-3.5 text-primary-500" />
              <span>Источники из базы знаний:</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.citations.map((citation) => (
                <div
                  key={citation.id}
                  className="p-2.5 rounded-xl bg-gray-50 border border-gray-200/60 text-xs hover:border-primary-200 transition"
                >
                  <span className="font-semibold text-gray-800 block truncate">
                    {citation.title}
                  </span>
                  {citation.sectionPath && (
                    <span className="text-[11px] text-gray-500 block truncate mt-0.5">
                      {citation.sectionPath}
                    </span>
                  )}
                  {citation.excerpt && (
                    <p className="text-[11px] text-gray-600 italic mt-1 line-clamp-2">
                      «{citation.excerpt}»
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TailGrids Feedback Toolbar (Shown only after streaming completes) */}
        {!message.isStreaming && message.content.length > 0 && (
          <div className="pt-2 flex flex-wrap items-center justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handleCopy}
              title="Копировать ответ"
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition cursor-pointer"
            >
              {isCopied ? (
                <>
                  <Check className="size-3.5 text-emerald-600" />
                  <span className="text-emerald-600">Скопировано!</span>
                </>
              ) : (
                <>
                  <Copy className="size-3.5" />
                  <span>Копировать</span>
                </>
              )}
            </button>

            {onRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate(message.id)}
                title="Перегенерировать ответ"
                className="size-7 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition cursor-pointer"
              >
                <RotateCw className="size-3.5" />
              </button>
            )}

            {/* Thumbs Up / Down */}
            <div className="flex items-center border-l border-gray-200 pl-1 ml-1">
              <button
                type="button"
                onClick={() => {
                  setFeedbackGiven('positive');
                  onFeedback?.(message.id, true);
                }}
                title="Полезный ответ"
                className={`size-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
                  feedbackGiven === 'positive'
                    ? 'text-emerald-600 bg-emerald-50'
                    : 'text-gray-500 hover:text-gray-800 hover:bg-gray-100'
                }`}
              >
                <ThumbsUp className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setFeedbackGiven('negative');
                  onFeedback?.(message.id, false);
                }}
                title="Ответ не помог"
                className={`size-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
                  feedbackGiven === 'negative'
                    ? 'text-red-600 bg-red-50'
                    : 'text-gray-500 hover:text-gray-800 hover:bg-gray-100'
                }`}
              >
                <ThumbsDown className="size-3.5" />
              </button>
            </div>
          </div>

          {/* Business Action Buttons: Вопрос решен / Позвать специалиста */}
          {message.needsFeedbackButtons && (
            <div className="flex items-center gap-2">
              {onResolveTicket && (
                <button
                  type="button"
                  onClick={onResolveTicket}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/70 hover:bg-emerald-100 transition cursor-pointer shadow-2xs active:scale-95"
                >
                  <CheckCircle2 className="size-3.5 text-emerald-600" />
                  <span>Вопрос решен</span>
                </button>
              )}

              {onEscalateToOperator && (
                isEscalated ? (
                  <span
                    title="Специалист уже вызван и подключается к диалогу"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500 border border-gray-200 cursor-not-allowed select-none"
                  >
                    <Headphones className="size-3.5 text-gray-400" />
                    <span>Специалист вызван</span>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={onEscalateToOperator}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-primary-50 text-primary-600 border border-primary-200/70 hover:bg-primary-100 transition cursor-pointer shadow-2xs active:scale-95"
                  >
                    <Headphones className="size-3.5 text-primary-500" />
                    <span>Позвать специалиста</span>
                  </button>
                )
              )}
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
};
