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
  ShieldCheck,
} from 'lucide-react';
import { Message } from '../../types/chat';
import { MarkdownView } from '../common/MarkdownView';

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
      <div className="flex flex-col space-y-2 py-3 bg-white border border-[#e5e5e5] rounded-none p-3.5">
        <div className="flex items-center gap-2">
          <div className="size-6 rounded-none bg-[#fef0ef] text-[#db2b21] flex items-center justify-center">
            <Sparkles className="size-3.5" />
          </div>
          <span className="text-xs font-bold text-[#264b82]">
            ИИ-Ассистент Портала Поставщиков
          </span>
          <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-none bg-[#eaf6ff] text-[#264b82] border border-[#b9dbf7]">
            ИИ-Бот
          </span>
        </div>
        <div className="flex items-center gap-1.5 pl-8">
          <div className="size-1.5 bg-[#264b82] animate-bounce [animation-delay:-0.3s]" />
          <div className="size-1.5 bg-[#264b82] animate-bounce [animation-delay:-0.15s]" />
          <div className="size-1.5 bg-[#264b82] animate-bounce" />
          <span className="text-xs text-[#264b82] font-semibold ml-2">
            {message.statusText || 'Поиск по базе регламентов...'}
          </span>
        </div>
      </div>
    );
  }

  // 2. System State
  if (message.type === 'system' || message.sender_type === 'system') {
    return (
      <div className="my-3 flex justify-center">
        <div className="max-w-xl px-4 py-2 rounded-none bg-[#fffbe6] border border-[#fbbd08]/50 text-[#1a1a1a] text-xs flex items-start gap-2.5">
          <AlertTriangle className="size-4 text-[#f67319] shrink-0 mt-0.5" />
          <div>
            <span className="font-bold block mb-0.5 text-[#1a1a1a]">Системное уведомление</span>
            <p className="leading-relaxed text-[#555555]">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // 3. User Message (Поставщик)
  if (message.type === 'user' || message.sender_type === 'client') {
    return (
      <div className="flex justify-end py-2 group w-full min-w-0">
        <div className="w-full max-w-2xl flex flex-col items-end min-w-0">
          <div className="flex items-center gap-1.5 mb-1 mr-1">
            <span className="text-[11px] font-bold text-[#7f8792]">Вы (Поставщик)</span>
          </div>
          {isEditing ? (
            <div className="w-full bg-white rounded-none p-3 border border-[#264b82]">
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full bg-transparent text-[14px] text-[#1a1a1a] outline-none resize-none min-h-[80px] p-2 border border-[#d4d4d5]"
              />
              <div className="flex justify-end gap-2 mt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsEditing(false);
                    setEditContent(message.content);
                  }}
                  className="px-3 py-1.5 text-xs font-bold rounded-none text-[#1a1a1a] border border-[#22242626] hover:bg-[#f2f7fc] transition cursor-pointer"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  className="px-3 py-1.5 text-xs font-bold rounded-none bg-[#db2b21] hover:bg-[#cd1f15] text-white transition cursor-pointer"
                >
                  Сохранить
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="bg-[#eaf6ff] border border-[#b9dbf7] rounded-none px-4 py-3 text-[#1a1a1a] text-[14px] max-w-full min-w-0 break-words">
                <MarkdownView content={message.content} />
              </div>

              {/* Action Buttons */}
              <div className="mt-1 flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
                <span className="text-[11px] text-[#7f8792] mr-1">{message.timestamp}</span>

                <button
                  type="button"
                  onClick={handleCopy}
                  title="Копировать"
                  className="size-6 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
                >
                  {isCopied ? <Check className="size-3.5 text-[#0d9b68]" /> : <Copy className="size-3.5" />}
                </button>

                {onEditMessage && (
                  <button
                    type="button"
                    onClick={() => setIsEditing(true)}
                    title="Редактировать вопрос"
                    className="size-6 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
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

  // 4. Incoming Message: Could be Bot, Operator, or Admin
  const isAdmin = message.sender_type === 'admin' || message.sender_role === 'admin';
  const isOperator =
    !isAdmin &&
    (message.sender_type === 'operator' ||
      message.sender_role === 'operator' ||
      message.sender_role === 'supervisor' ||
      message.id.startsWith('op-') ||
      message.id.startsWith('operator-'));
  const isBot = !isAdmin && !isOperator;

  const senderConfig = isAdmin
    ? {
        title: message.sender_name || 'Администратор Портала',
        badge: 'Администратор',
        badgeClass: 'bg-[#f3e8ff] text-[#6b21a8] border-[#d8b4fe]',
        iconBgClass: 'bg-[#6b21a8] text-white',
        titleColorClass: 'text-[#6b21a8]',
        bubbleBorderClass: 'border-l-4 border-l-[#6b21a8]',
        Icon: ShieldCheck,
      }
    : isOperator
    ? {
        title: message.sender_name || 'Оператор службы поддержки',
        badge: 'Оператор поддержки',
        badgeClass: 'bg-[#e7f8f2] text-[#0d9b68] border-[#a3e3cb]',
        iconBgClass: 'bg-[#0d9b68] text-white',
        titleColorClass: 'text-[#0d9b68]',
        bubbleBorderClass: 'border-l-4 border-l-[#0d9b68]',
        Icon: Headphones,
      }
    : {
        title: message.sender_name || 'ИИ-Ассистент Портала Поставщиков',
        badge: 'ИИ-Бот',
        badgeClass: 'bg-[#eaf6ff] text-[#264b82] border-[#b9dbf7]',
        iconBgClass: 'bg-[#264b82] text-white',
        titleColorClass: 'text-[#264b82]',
        bubbleBorderClass: '',
        Icon: Sparkles,
      };

  const SenderIcon = senderConfig.Icon;

  return (
    <div className="flex flex-col space-y-2 py-3 group w-full min-w-0">
      {/* Sender Header */}
      <div className="flex items-center gap-2">
        <div className={`size-6 rounded-none ${senderConfig.iconBgClass} flex items-center justify-center shrink-0`}>
          <SenderIcon className="size-3.5" />
        </div>
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-xs font-bold ${senderConfig.titleColorClass} truncate`}>
            {senderConfig.title}
          </span>
          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded-none border ${senderConfig.badgeClass} shrink-0`}>
            {senderConfig.badge}
          </span>
        </div>
        <span className="text-[11px] text-[#7f8792] ml-auto shrink-0">{message.timestamp}</span>
      </div>

      {/* Message Content Bubble */}
      <div className={`bg-white border border-[#e5e5e5] ${senderConfig.bubbleBorderClass} rounded-none p-4 text-[#1a1a1a] text-[14px] leading-relaxed space-y-3 min-w-0`}>
        {message.isStreaming ? (
          <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {message.content}
            <span
              aria-hidden="true"
              className="inline-block w-1.5 h-4 ml-1 bg-[#db2b21] animate-pulse align-middle"
            />
          </div>
        ) : (
          <MarkdownView content={message.content} />
        )}

        {/* RAG Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-[#e5e5e5] space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#264b82]">
              <BookOpen className="size-3.5 text-[#264b82]" />
              <span>Источники из регламентов:</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.citations.map((citation) => (
                <div
                  key={citation.id}
                  className="p-2.5 rounded-none bg-[#f7f8f9] border border-[#dddddd] text-xs hover:border-[#264b82] transition"
                >
                  <span className="font-bold text-[#1a1a1a] block truncate">
                    {citation.title}
                  </span>
                  {citation.sectionPath && (
                    <span className="text-[11px] text-[#7f8792] block truncate mt-0.5">
                      {citation.sectionPath}
                    </span>
                  )}
                  {citation.excerpt && (
                    <p className="text-[11px] text-[#555555] italic mt-1 line-clamp-2">
                      «{citation.excerpt}»
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action Toolbar */}
        {!message.isStreaming && message.content.length > 0 && (
          <div className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#e5e5e5]">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleCopy}
                title="Копировать ответ"
                className="flex items-center gap-1 px-2 py-1 rounded-none text-xs font-semibold text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
              >
                {isCopied ? (
                  <>
                    <Check className="size-3.5 text-[#0d9b68]" />
                    <span className="text-[#0d9b68]">Скопировано</span>
                  </>
                ) : (
                  <>
                    <Copy className="size-3.5" />
                    <span>Копировать</span>
                  </>
                )}
              </button>

              {/* Only show regenerate for bot messages */}
              {isBot && onRegenerate && (
                <button
                  type="button"
                  onClick={() => onRegenerate(message.id)}
                  title="Перегенерировать ответ"
                  className="size-6 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
                >
                  <RotateCw className="size-3.5" />
                </button>
              )}

              {/* Thumbs Up / Down */}
              <div className="flex items-center border-l border-[#dddddd] pl-1 ml-1">
                <button
                  type="button"
                  onClick={() => {
                    setFeedbackGiven('positive');
                    onFeedback?.(message.id, true);
                  }}
                  title="Полезный ответ"
                  className={`size-6 rounded-none flex items-center justify-center transition cursor-pointer ${
                    feedbackGiven === 'positive'
                      ? 'text-[#0d9b68] bg-[#e7f8f2]'
                      : 'text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc]'
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
                  className={`size-6 rounded-none flex items-center justify-center transition cursor-pointer ${
                    feedbackGiven === 'negative'
                      ? 'text-[#db2b21] bg-[#fef0ef]'
                      : 'text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc]'
                  }`}
                >
                  <ThumbsDown className="size-3.5" />
                </button>
              </div>
            </div>

            {/* Business Action Buttons: Вопрос решен / Позвать специалиста */}
            {message.needsFeedbackButtons ? (
              <div className="flex items-center gap-2">
                {onResolveTicket && (
                  <button
                    type="button"
                    onClick={onResolveTicket}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-[#0d9b68] bg-transparent hover:bg-[#e7f8f2] border border-[#0d9b68] transition cursor-pointer"
                  >
                    <CheckCircle2 className="size-3.5 text-[#0d9b68]" />
                    <span>Вопрос решен</span>
                  </button>
                )}

                {isBot && onEscalateToOperator && (
                  isEscalated ? (
                    <span
                      title="Специалист уже вызван и подключается к диалогу"
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold bg-[#eeeeee] text-[#7f8792] border border-[#d4d4d5] cursor-not-allowed select-none"
                    >
                      <Headphones className="size-3.5 text-[#7f8792]" />
                      <span>Специалист вызван</span>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={onEscalateToOperator}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-[#264b82] bg-transparent hover:bg-[#eaf6ff] border border-[#264b82] transition cursor-pointer"
                    >
                      <Headphones className="size-3.5 text-[#264b82]" />
                      <span>Позвать специалиста</span>
                    </button>
                  )
                )}
              </div>
            ) : (
              !isBot && onResolveTicket && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onResolveTicket}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-[#0d9b68] bg-transparent hover:bg-[#e7f8f2] border border-[#0d9b68] transition cursor-pointer"
                  >
                    <CheckCircle2 className="size-3.5 text-[#0d9b68]" />
                    <span>Вопрос решен</span>
                  </button>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
};
