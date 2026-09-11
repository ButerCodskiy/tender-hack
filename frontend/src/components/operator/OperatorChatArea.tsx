import React, { useRef, useEffect } from 'react';
import {
  Send,
  CheckCircle2,
  ArrowRightLeft,
  Headphones,
  User,
  Sparkles,
  AlertTriangle,
  Building2,
  Clock,
  ShieldAlert,
} from 'lucide-react';
import { OperatorTicketWorkspace, TicketPriority } from '../../types/operator';

interface OperatorChatAreaProps {
  workspace: OperatorTicketWorkspace | null;
  isLoading: boolean;
  draftText: string;
  onDraftChange: (text: string) => void;
  onSendMessage: () => Promise<void>;
  onTransferClick: () => void;
  onResolveClick: () => void;
  isSending: boolean;
}

export const OperatorChatArea: React.FC<OperatorChatAreaProps> = ({
  workspace,
  isLoading,
  draftText,
  onDraftChange,
  onSendMessage,
  onTransferClick,
  onResolveClick,
  isSending,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [workspace?.messages]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (draftText.trim() && !isSending) {
        onSendMessage();
      }
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50/50">
        <div className="flex flex-col items-center gap-3 text-gray-500">
          <div className="size-8 rounded-full border-2 border-primary-600 border-t-transparent animate-spin" />
          <span className="text-xs font-medium">Загрузка обращения и контекста...</span>
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50/30 p-6 text-center">
        <div className="max-w-sm space-y-3">
          <div className="size-12 rounded-2xl bg-primary-50 text-primary-600 flex items-center justify-center mx-auto shadow-2xs">
            <Headphones className="size-6" />
          </div>
          <h3 className="text-base font-bold text-title-50">Обращение не выбрано</h3>
          <p className="text-xs text-gray-500 leading-relaxed">
            Выберите тикет из списка слева, чтобы просмотреть переписку с клиентом, рекомендации ИИ и ответить на запрос.
          </p>
        </div>
      </div>
    );
  }

  const getPriorityBadge = (p: TicketPriority) => {
    switch (p) {
      case 'P0':
        return {
          label: 'P0 Критический',
          badge: 'bg-red-50 text-red-600 border-red-200 font-bold',
          icon: ShieldAlert,
        };
      case 'P1':
        return {
          label: 'P1 Срочный',
          badge: 'bg-amber-50 text-amber-700 border-amber-200 font-semibold',
          icon: AlertTriangle,
        };
      case 'P2':
        return {
          label: 'P2 Стандарт',
          badge: 'bg-primary-50 text-primary-600 border-primary-200 font-medium',
          icon: Clock,
        };
    }
  };

  const prio = getPriorityBadge(workspace.priority);
  const PrioIcon = prio.icon;

  return (
    <div className="flex-1 flex flex-col h-dvh bg-gray-50/40 overflow-hidden">
      {/* Ticket Header */}
      <div className="h-16 px-6 border-b border-gray-100 bg-white flex items-center justify-between shrink-0 shadow-2xs z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="size-10 rounded-xl bg-gray-100 border border-gray-200/80 flex items-center justify-center text-gray-600 shrink-0">
            <Building2 className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-title-50 truncate">
                {workspace.client.company_name || 'Поставщик без названия'}
              </span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border flex items-center gap-1 shrink-0 ${prio.badge}`}>
                <PrioIcon className="size-3" />
                <span>{prio.label}</span>
              </span>
              <span className="text-xs font-mono text-gray-400 shrink-0">
                #{workspace.ticket_id}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
              <span>{workspace.client.full_name || 'Представитель'}</span>
              <span>•</span>
              <span className="font-mono text-[11px] text-gray-400">ИНН {workspace.client.inn || '—'}</span>
            </div>
          </div>
        </div>

        {/* Action Buttons: Transfer & Resolve */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onTransferClick}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition cursor-pointer shadow-2xs"
            title="Передать тикет на другую линию или специалисту"
          >
            <ArrowRightLeft className="size-3.5 text-gray-500" />
            <span>Перевести</span>
          </button>

          <button
            type="button"
            onClick={onResolveClick}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 transition cursor-pointer shadow-2xs active:scale-95"
            title="Завершить обработку обращения"
          >
            <CheckCircle2 className="size-3.5" />
            <span>Вопрос решен</span>
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
        {workspace.messages.map((msg) => {
          const isSystem = msg.type === 'system' || msg.sender_type === 'system';
          const isClient = msg.sender_type === 'client' || msg.type === 'user';
          const isBot = msg.sender_type === 'bot' || (msg.id.startsWith('bot-') && msg.sender_type !== 'operator');

          // 1. System notification
          if (isSystem) {
            return (
              <div key={msg.id} className="flex justify-center my-2">
                <div className="px-3.5 py-1.5 rounded-full bg-amber-50 border border-amber-200 text-[11px] text-amber-800 flex items-center gap-1.5 shadow-2xs">
                  <AlertTriangle className="size-3 text-amber-600" />
                  <span>{msg.content}</span>
                  <span className="text-amber-500 font-mono text-[10px] ml-1">({msg.timestamp})</span>
                </div>
              </div>
            );
          }

          // 2. Client (User) message: Left-aligned
          if (isClient) {
            return (
              <div key={msg.id} className="flex items-start gap-2.5 max-w-2xl">
                <div className="size-8 rounded-full bg-primary-50 border border-primary-200 flex items-center justify-center text-primary-700 shrink-0 font-bold text-xs mt-0.5">
                  <User className="size-4" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-gray-800">
                      {workspace.client.full_name || 'Клиент'}
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono">{msg.timestamp}</span>
                  </div>
                  <div className="p-3.5 rounded-2xl rounded-tl-sm bg-white border border-gray-200 text-xs md:text-sm text-gray-800 shadow-2xs leading-relaxed break-words [overflow-wrap:anywhere]">
                    {msg.content}
                  </div>
                </div>
              </div>
            );
          }

          // 3. AI Bot message: Left-aligned with distinctive bot styling
          if (isBot) {
            return (
              <div key={msg.id} className="flex items-start gap-2.5 max-w-2xl">
                <div className="size-8 rounded-full bg-gradient-to-tr from-primary-600 to-primary-400 flex items-center justify-center text-white shrink-0 shadow-2xs mt-0.5">
                  <Sparkles className="size-4" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-primary-700">
                      ИИ-Ассистент (автоответ)
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono">{msg.timestamp}</span>
                  </div>
                  <div className="p-3.5 rounded-2xl rounded-tl-sm bg-primary-50/40 border border-primary-100 text-xs md:text-sm text-gray-800 shadow-2xs leading-relaxed break-words [overflow-wrap:anywhere]">
                    {msg.content}
                  </div>
                </div>
              </div>
            );
          }

          // 4. Operator message: Right-aligned
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="flex items-start gap-2.5 max-w-2xl flex-row-reverse">
                <div className="size-8 rounded-full bg-primary-600 flex items-center justify-center text-white shrink-0 font-bold text-xs mt-0.5 shadow-2xs">
                  <Headphones className="size-4" />
                </div>
                <div className="space-y-1 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="text-[10px] text-gray-400 font-mono">{msg.timestamp}</span>
                    <span className="text-xs font-semibold text-gray-800">
                      Вы (Оператор)
                    </span>
                  </div>
                  <div className="p-3.5 rounded-2xl rounded-tr-sm bg-primary-600 text-white text-xs md:text-sm shadow-2xs leading-relaxed text-left break-words [overflow-wrap:anywhere]">
                    {msg.content}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Response Composer */}
      <div className="p-4 border-t border-gray-100 bg-white shrink-0">
        <div className="relative rounded-2xl border border-gray-200 bg-white focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-100 transition shadow-2xs">
          <textarea
            value={draftText}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Введите ответ клиенту..."
            rows={3}
            className="w-full p-3.5 pb-12 bg-transparent text-xs md:text-sm text-gray-800 placeholder-gray-400 outline-none resize-none leading-relaxed"
          />

          <div className="absolute bottom-2.5 left-3 right-3 flex items-center justify-between">
            <button
              type="button"
              disabled={!draftText.trim() || isSending}
              onClick={() => {
                if (draftText.trim() && !isSending) {
                  onSendMessage();
                }
              }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer shadow-xs active:scale-95"
            >
              <span>{isSending ? 'Отправка...' : 'Отправить ответ'}</span>
              <Send className="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
