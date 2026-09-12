import React, { useState } from 'react';
import {
  Sparkles,
  Building2,
  Copy,
  Check,
  BookOpen,
  History,
  CornerDownLeft,
  Mail,
  Phone,
  FileText,
  BadgePercent,
  Layers,
} from 'lucide-react';
import { OperatorTicketWorkspace } from '../../types/operator';

interface OperatorCopilotPanelProps {
  workspace: OperatorTicketWorkspace | null;
  onUseSuggestedResponse: (text: string) => void;
}

export const OperatorCopilotPanel: React.FC<OperatorCopilotPanelProps> = ({
  workspace,
  onUseSuggestedResponse,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const handleCopy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1800);
    } catch (e) {
      console.error('Ошибка копирования:', e);
    }
  };

  if (!workspace) {
    return (
      <aside className="w-88 border-l border-[#e5e5e5] bg-white h-dvh p-6 flex flex-col justify-center items-center text-center select-none shrink-0">
        <Sparkles className="size-10 text-[#cccccc] mb-3" />
        <span className="text-xs font-bold text-[#666666]">
          Контекст и ИИ-Копилот
        </span>
        <p className="text-[11px] text-[#888888] mt-1 max-w-[200px]">
          Выберите обращение, чтобы увидеть данные контрагента и рекомендации
        </p>
      </aside>
    );
  }

  const { client, copilot_summary } = workspace;

  return (
    <aside className="w-96 border-l border-[#e5e5e5] bg-[#f7f8f9] h-dvh flex flex-col shrink-0 select-none overflow-hidden z-10">
      {/* Panel Header */}
      <div className="h-14 px-4 border-b border-[#e5e5e5] flex items-center justify-between shrink-0 bg-white">
        <div className="flex items-center gap-2.5">
          <div className="size-7 rounded-none bg-[#264b82] flex items-center justify-center text-white">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h2 className="text-xs font-bold text-[#1a1a1a]">ИИ-Копилот и Контекст</h2>
            <span className="text-[10px] text-[#666666]">Аналитика обращения</span>
          </div>
        </div>
        {copilot_summary?.suggested_line_code && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-none bg-[#eaf6ff] text-[#264b82] font-bold border border-[#b9dbf7]">
            Линия: {copilot_summary.suggested_line_code}
          </span>
        )}
      </div>

      {/* Scrollable Context Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {/* 1. Client & Company Profile Card */}
        <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#1a1a1a]">
              <Building2 className="size-3.5 text-[#264b82]" />
              <span>Карточка контрагента</span>
            </div>
            {client.inn && (
              <button
                type="button"
                onClick={() => handleCopy(client.inn || '', 'inn')}
                className="flex items-center gap-1 text-[10px] font-mono text-[#666666] hover:text-[#264b82] transition cursor-pointer"
                title="Скопировать ИНН"
              >
                <span>ИНН {client.inn}</span>
                {copiedKey === 'inn' ? (
                  <Check className="size-3 text-[#166534]" />
                ) : (
                  <Copy className="size-3" />
                )}
              </button>
            )}
          </div>

          <div className="space-y-1.5 text-xs">
            <div>
              <span className="text-[10px] text-[#666666] block">Организация:</span>
              <span className="font-semibold text-[#1a1a1a]">
                {client.company_name || '—'}
              </span>
            </div>

            {client.full_name && (
              <div>
                <span className="text-[10px] text-[#666666] block">Контактное лицо:</span>
                <span className="text-[#333333]">{client.full_name}</span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-1 pt-1.5 text-[11px] text-[#333333] border-t border-[#e5e5e5]">
              {client.phone && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Phone className="size-3 text-[#888888]" />
                    <span>{client.phone}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopy(client.phone || '', 'phone')}
                    className="text-[#888888] hover:text-[#264b82] cursor-pointer"
                  >
                    {copiedKey === 'phone' ? <Check className="size-3 text-[#166534]" /> : <Copy className="size-3" />}
                  </button>
                </div>
              )}
              {client.email && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 truncate">
                    <Mail className="size-3 text-[#888888] shrink-0" />
                    <span className="truncate">{client.email}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopy(client.email, 'email')}
                    className="text-[#888888] hover:text-[#264b82] cursor-pointer ml-1"
                  >
                    {copiedKey === 'email' ? <Check className="size-3 text-[#166534]" /> : <Copy className="size-3" />}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 2. Problem Essence Summary */}
        {copilot_summary?.summary && (
          <div className="p-3.5 rounded-none bg-white border border-[#b9dbf7] space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#264b82]">
              <Sparkles className="size-3.5 text-[#264b82]" />
              <span>Суть проблемы (ИИ-анализ)</span>
            </div>
            <p className="text-xs text-[#1a1a1a] leading-relaxed">
              {copilot_summary.summary}
            </p>
          </div>
        )}

        {/* 3. Suggested Response Draft */}
        {copilot_summary?.suggested_response && (
          <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-bold text-[#1a1a1a]">
                <FileText className="size-3.5 text-[#264b82]" />
                <span>Рекомендуемый ответ</span>
              </div>
              <button
                type="button"
                onClick={() => onUseSuggestedResponse(copilot_summary.suggested_response || '')}
                className="flex items-center gap-1 px-2.5 py-1 rounded-none bg-[#264b82] hover:bg-[#1c3f72] text-white text-[10px] font-bold transition cursor-pointer"
                title="Вставить сгенерированный текст в поле ввода"
              >
                <CornerDownLeft className="size-3" />
                <span>Вставить в ответ</span>
              </button>
            </div>
            <p className="text-xs text-[#1a1a1a] leading-relaxed bg-[#f7f8f9] p-2.5 rounded-none border border-[#e5e5e5] break-words [overflow-wrap:anywhere]">
              {copilot_summary.suggested_response}
            </p>
          </div>
        )}

        {/* 4. Recommended Articles & Regulation Chunks */}
        {copilot_summary?.recommended_chunk_ids && copilot_summary.recommended_chunk_ids.length > 0 && (
          <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#1a1a1a]">
              <BookOpen className="size-3.5 text-[#264b82]" />
              <span>Связанные регламенты и статьи</span>
            </div>
            <div className="space-y-1.5">
              {copilot_summary.recommended_chunk_ids.map((chunkId, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded-none bg-[#f7f8f9] border border-[#e5e5e5] flex items-center justify-between text-xs hover:border-[#264b82] transition"
                >
                  <div className="flex items-center gap-2 truncate">
                    <Layers className="size-3 text-[#888888] shrink-0" />
                    <span className="font-mono text-[11px] text-[#1a1a1a] truncate">{chunkId}</span>
                  </div>
                  <span className="text-[10px] font-semibold text-[#264b82]">База знаний</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. Similar Resolved Tickets (Qdrant) */}
        {copilot_summary?.similar_resolved_tickets && copilot_summary.similar_resolved_tickets.length > 0 && (
          <div className="p-3.5 rounded-none bg-white border border-[#e5e5e5] space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#1a1a1a]">
              <History className="size-3.5 text-[#264b82]" />
              <span>Похожие решенные кейсы</span>
            </div>
            <div className="space-y-2">
              {copilot_summary.similar_resolved_tickets.map((similar) => {
                const scorePercent = Math.round(similar.similarity_score * 100);
                return (
                  <div
                    key={similar.ticket_id}
                    className="p-2.5 rounded-none bg-[#f7f8f9] border border-[#e5e5e5] text-xs space-y-1.5 hover:border-[#999999] transition"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-[#666666]">
                        #{similar.ticket_id} • {similar.support_line}
                      </span>
                      <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-none bg-[#f0fdf4] text-[#166534] border border-[#bbf7d0] font-semibold text-[10px]">
                        <BadgePercent className="size-3 text-[#166534]" />
                        <span>{scorePercent}% сходства</span>
                      </span>
                    </div>

                    <p className="font-medium text-[#1a1a1a] text-[11px] leading-snug">
                      «{similar.user_query}»
                    </p>

                    <div className="p-2 rounded-none bg-white border border-[#e5e5e5] text-[11px] text-[#333333] leading-relaxed">
                      <span className="font-semibold block text-[10px] text-[#166534] mb-0.5">Решение:</span>
                      {similar.solution_text}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
