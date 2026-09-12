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
import { MarkdownView } from '../common/MarkdownView';

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
          badge: 'bg-[#fef0ef] text-[#db2b21] border-[#db2b21]/40 font-bold',
          icon: ShieldAlert,
        };
      case 'P1':
        return {
          label: 'P1 Срочный',
          badge: 'bg-[#fff3ec] text-[#f67319] border-[#f67319]/40 font-bold',
          icon: AlertTriangle,
        };
      case 'P2':
        return {
          label: 'P2 Стандарт',
          badge: 'bg-[#eaf6ff] text-[#264b82] border-[#264b82]/30 font-bold',
          icon: Clock,
        };
    }
  };

  const prio = getPriorityBadge(workspace.priority);
  const PrioIcon = prio.icon;

  return (
    <div className="flex-1 flex flex-col h-dvh bg-[#f7f8f9] overflow-hidden">
      {/* Ticket Header */}
      <div className="h-14 px-5 border-b border-[#e5e5e5] bg-white flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="size-8 rounded-none bg-[#f7f8f9] border border-[#dddddd] flex items-center justify-center text-[#264b82] shrink-0">
            <Building2 className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#1a1a1a] truncate">
                {workspace.client.company_name || 'Поставщик без названия'}
              </span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border flex items-center gap-1 shrink-0 ${prio.badge}`}>
                <PrioIcon className="size-3" />
                <span>{prio.label}</span>
              </span>
              <span className="text-xs font-mono text-[#7f8792] shrink-0">
                #{workspace.ticket_id}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-[#7f8792] mt-0.5">
              <span>{workspace.client.full_name || 'Представитель'}</span>
              <span>•</span>
              <span className="font-mono text-[11px]">ИНН {workspace.client.inn || '—'}</span>
            </div>
          </div>
        </div>

        {/* Action Buttons: Transfer & Resolve */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onTransferClick}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-[#264b82] bg-white border border-[#264b82] hover:bg-[#eaf6ff] transition cursor-pointer"
            title="Передать тикет на другую линию или специалисту"
          >
            <ArrowRightLeft className="size-3.5 text-[#264b82]" />
            <span>Перевести</span>
          </button>

          <button
            type="button"
            onClick={onResolveClick}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-none text-xs font-bold text-white bg-[#0d9b68] hover:bg-[#05895a] transition cursor-pointer"
            title="Завершить обработку обращения"
          >
            <CheckCircle2 className="size-3.5" />
            <span>Вопрос решен</span>
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-5 space-y-3 custom-scrollbar">
        {workspace.messages.map((msg) => {
          const isSystem = msg.type === 'system' || msg.sender_type === 'system';
          const isClient = msg.sender_type === 'client' || msg.type === 'user';
          const isAdmin = msg.sender_type === 'admin' || msg.sender_role === 'admin';
          const isBot =
            !isAdmin &&
            (msg.sender_type === 'bot' ||
              (msg.id.startsWith('bot-') && msg.sender_type !== 'operator'));

          // 1. System notification
          if (isSystem) {
            return (
              <div key={msg.id} className="flex justify-center my-2">
                <div className="px-3.5 py-1.5 rounded-none bg-[#fffbe6] border border-[#fbbd08]/50 text-[11px] text-[#1a1a1a] flex items-center gap-1.5">
                  <AlertTriangle className="size-3 text-[#f67319]" />
                  <span>{msg.content}</span>
                  <span className="text-[#7f8792] font-mono text-[10px] ml-1">({msg.timestamp})</span>
                </div>
              </div>
            );
          }

          // 2. Client (User) message: Left-aligned
          if (isClient) {
            return (
              <div key={msg.id} className="flex items-start gap-2.5 max-w-2xl">
                <div className="size-7 rounded-full bg-[#eaf6ff] border border-[#b9dbf7] flex items-center justify-center text-[#264b82] shrink-0 font-bold text-xs mt-0.5">
                  <User className="size-3.5" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#1a1a1a]">
                      {workspace.client.full_name || 'Клиент'}
                    </span>
                    <span className="text-[10px] text-[#7f8792] font-mono">{msg.timestamp}</span>
                  </div>
                  <div className="p-3.5 rounded-none bg-[#eaf6ff] border border-[#b9dbf7] text-xs md:text-[13px] text-[#1a1a1a] leading-relaxed break-words [overflow-wrap:anywhere]">
                    <MarkdownView content={msg.content} />
                  </div>
                </div>
              </div>
            );
          }

          // 3. Admin message: Left-aligned with distinctive purple styling
          if (isAdmin) {
            return (
              <div key={msg.id} className="flex items-start gap-2.5 max-w-2xl">
                <div className="size-7 rounded-none bg-[#6b21a8] flex items-center justify-center text-white shrink-0 mt-0.5">
                  <ShieldAlert className="size-3.5" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#6b21a8]">
                      {msg.sender_name || 'Администратор'}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded-none bg-[#f3e8ff] text-[#6b21a8] border border-[#d8b4fe] font-bold">
                      Администратор
                    </span>
                    <span className="text-[10px] text-[#7f8792] font-mono">{msg.timestamp}</span>
                  </div>
                  <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] border-l-4 border-l-[#6b21a8] text-xs md:text-[13px] text-[#1a1a1a] leading-relaxed break-words [overflow-wrap:anywhere]">
                    <MarkdownView content={msg.content} />
                  </div>
                </div>
              </div>
            );
          }

          // 4. AI Bot message: Left-aligned with distinctive bot styling
          if (isBot) {
            return (
              <div key={msg.id} className="flex items-start gap-2.5 max-w-2xl">
                <div className="size-7 rounded-none bg-[#264b82] flex items-center justify-center text-white shrink-0 mt-0.5">
                  <Sparkles className="size-3.5" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#264b82]">
                      ИИ-Ассистент (автоответ)
                    </span>
                    <span className="text-[10px] text-[#7f8792] font-mono">{msg.timestamp}</span>
                  </div>
                  <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] text-xs md:text-[13px] text-[#1a1a1a] leading-relaxed break-words [overflow-wrap:anywhere]">
                    <MarkdownView content={msg.content} />
                  </div>
                </div>
              </div>
            );
          }

          // 4. Operator message: Right-aligned
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="flex items-start gap-2.5 max-w-2xl flex-row-reverse">
                <div className="size-7 rounded-full bg-[#264b82] flex items-center justify-center text-white shrink-0 font-bold text-xs mt-0.5">
                  <Headphones className="size-3.5" />
                </div>
                <div className="space-y-1 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="text-[10px] text-[#7f8792] font-mono">{msg.timestamp}</span>
                    <span className="text-xs font-bold text-[#1a1a1a]">
                      Вы (Оператор)
                    </span>
                  </div>
                  <div className="p-3.5 rounded-none bg-[#264b82] text-white text-xs md:text-[13px] leading-relaxed text-left break-words [overflow-wrap:anywhere]">
                    <MarkdownView
                      content={msg.content}
                      className="text-white [&_*]:text-white [&_a]:text-[#b9dbf7] [&_code]:bg-[#1c3f72] [&_code]:text-white [&_pre]:bg-[#1c3f72] [&_pre]:border-[#3b669f] [&_table]:text-white [&_th]:bg-[#1c3f72] [&_th]:border-[#3b669f] [&_td]:border-[#3b669f]"
                    />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Response Composer */}
      <div className="p-3 border-t border-[#e5e5e5] bg-white shrink-0">
        <div className="relative rounded-none border border-[#d4d4d5] bg-white focus-within:border-[#264b82] transition">
          <textarea
            value={draftText}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Введите ответ клиенту..."
            rows={3}
            className="w-full p-3 pb-10 bg-transparent text-xs md:text-[13px] text-[#1a1a1a] placeholder-[#7f8792] outline-none resize-none leading-relaxed"
          />

          <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between">
            <button
              type="button"
              disabled={!draftText.trim() || isSending}
              onClick={() => {
                if (draftText.trim() && !isSending) {
                  onSendMessage();
                }
              }}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-none text-xs font-bold bg-[#db2b21] text-white hover:bg-[#cd1f15] active:bg-[#af221a] disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
            >
              <span>{isSending ? 'Отправка...' : 'Отправить ответ'}</span>
              <Send className="size-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
