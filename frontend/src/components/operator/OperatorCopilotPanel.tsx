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
      <aside className="w-88 border-l border-gray-100 bg-white h-dvh p-6 flex flex-col justify-center items-center text-center select-none shrink-0">
        <Sparkles className="size-10 text-gray-300 mb-3" />
        <span className="text-xs font-semibold text-gray-400">
          Контекст и ИИ-Копилот
        </span>
        <p className="text-[11px] text-gray-400 mt-1 max-w-[200px]">
          Выберите обращение, чтобы увидеть данные контрагента и рекомендации
        </p>
      </aside>
    );
  }

  const { client, copilot_summary } = workspace;

  return (
    <aside className="w-96 border-l border-gray-100 bg-white h-dvh flex flex-col shrink-0 select-none overflow-hidden shadow-2xs z-10">
      {/* Panel Header */}
      <div className="h-16 px-5 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
        <div className="flex items-center gap-2">
          <div className="size-8 rounded-xl bg-gradient-to-tr from-primary-600 to-indigo-500 flex items-center justify-center text-white shadow-2xs">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h2 className="text-xs font-bold text-title-50">ИИ-Копилот и Контекст</h2>
            <span className="text-[10px] text-gray-400">Аналитика обращения</span>
          </div>
        </div>
        {copilot_summary?.suggested_line_code && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-bold border border-indigo-200">
            Линия: {copilot_summary.suggested_line_code}
          </span>
        )}
      </div>

      {/* Scrollable Context Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {/* 1. Client & Company Profile Card */}
        <div className="p-3.5 rounded-2xl bg-gray-50/70 border border-gray-100 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-bold text-gray-800">
              <Building2 className="size-3.5 text-primary-600" />
              <span>Карточка контрагента</span>
            </div>
            {client.inn && (
              <button
                type="button"
                onClick={() => handleCopy(client.inn || '', 'inn')}
                className="flex items-center gap-1 text-[10px] font-mono text-gray-500 hover:text-primary-600 transition cursor-pointer"
                title="Скопировать ИНН"
              >
                <span>ИНН {client.inn}</span>
                {copiedKey === 'inn' ? (
                  <Check className="size-3 text-emerald-600" />
                ) : (
                  <Copy className="size-3" />
                )}
              </button>
            )}
          </div>

          <div className="space-y-1.5 text-xs">
            <div>
              <span className="text-[10px] text-gray-400 block">Организация:</span>
              <span className="font-semibold text-gray-800">
                {client.company_name || '—'}
              </span>
            </div>

            {client.full_name && (
              <div>
                <span className="text-[10px] text-gray-400 block">Контактное лицо:</span>
                <span className="text-gray-700">{client.full_name}</span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-1 pt-1 text-[11px] text-gray-600 border-t border-gray-100">
              {client.phone && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Phone className="size-3 text-gray-400" />
                    <span>{client.phone}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopy(client.phone || '', 'phone')}
                    className="text-gray-400 hover:text-primary-600 cursor-pointer"
                  >
                    {copiedKey === 'phone' ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
                  </button>
                </div>
              )}
              {client.email && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 truncate">
                    <Mail className="size-3 text-gray-400 shrink-0" />
                    <span className="truncate">{client.email}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopy(client.email, 'email')}
                    className="text-gray-400 hover:text-primary-600 cursor-pointer ml-1"
                  >
                    {copiedKey === 'email' ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 2. Problem Essence Summary */}
        {copilot_summary?.summary && (
          <div className="p-3.5 rounded-2xl bg-indigo-50/40 border border-indigo-100 space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-900">
              <Sparkles className="size-3.5 text-indigo-600" />
              <span>Суть проблемы (ИИ-анализ)</span>
            </div>
            <p className="text-xs text-indigo-950/80 leading-relaxed">
              {copilot_summary.summary}
            </p>
          </div>
        )}

        {/* 3. Suggested Response Draft */}
        {copilot_summary?.suggested_response && (
          <div className="p-3.5 rounded-2xl bg-primary-50/40 border border-primary-100 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-bold text-primary-900">
                <FileText className="size-3.5 text-primary-600" />
                <span>Рекомендуемый ответ</span>
              </div>
              <button
                type="button"
                onClick={() => onUseSuggestedResponse(copilot_summary.suggested_response || '')}
                className="flex items-center gap-1 px-2 py-1 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-[10px] font-semibold transition cursor-pointer shadow-2xs active:scale-95"
                title="Вставить сгенерированный текст в поле ввода"
              >
                <CornerDownLeft className="size-3" />
                <span>Вставить в ответ</span>
              </button>
            </div>
            <p className="text-xs text-gray-700 leading-relaxed bg-white/80 p-2.5 rounded-xl border border-primary-100/60 break-words [overflow-wrap:anywhere]">
              {copilot_summary.suggested_response}
            </p>
          </div>
        )}

        {/* 4. Recommended Articles & Regulation Chunks */}
        {copilot_summary?.recommended_chunk_ids && copilot_summary.recommended_chunk_ids.length > 0 && (
          <div className="p-3.5 rounded-2xl bg-gray-50/70 border border-gray-100 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-gray-800">
              <BookOpen className="size-3.5 text-primary-600" />
              <span>Связанные регламенты и статьи</span>
            </div>
            <div className="space-y-1.5">
              {copilot_summary.recommended_chunk_ids.map((chunkId, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded-xl bg-white border border-gray-200/80 flex items-center justify-between text-xs hover:border-primary-200 transition"
                >
                  <div className="flex items-center gap-2 truncate">
                    <Layers className="size-3 text-gray-400 shrink-0" />
                    <span className="font-mono text-[11px] text-gray-700 truncate">{chunkId}</span>
                  </div>
                  <span className="text-[10px] font-semibold text-primary-600">База знаний</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. Similar Resolved Tickets (Qdrant) */}
        {copilot_summary?.similar_resolved_tickets && copilot_summary.similar_resolved_tickets.length > 0 && (
          <div className="p-3.5 rounded-2xl bg-gray-50/70 border border-gray-100 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-gray-800">
              <History className="size-3.5 text-primary-600" />
              <span>Похожие решенные кейсы</span>
            </div>
            <div className="space-y-2">
              {copilot_summary.similar_resolved_tickets.map((similar) => {
                const scorePercent = Math.round(similar.similarity_score * 100);
                return (
                  <div
                    key={similar.ticket_id}
                    className="p-2.5 rounded-xl bg-white border border-gray-200 text-xs space-y-1.5 shadow-2xs hover:border-gray-300 transition"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-gray-400">
                        #{similar.ticket_id} • {similar.support_line}
                      </span>
                      <span className="flex items-center gap-0.5 px-1.5 py-0.2 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold text-[10px]">
                        <BadgePercent className="size-3 text-emerald-600" />
                        <span>{scorePercent}% сходства</span>
                      </span>
                    </div>

                    <p className="font-medium text-gray-800 text-[11px] leading-snug">
                      «{similar.user_query}»
                    </p>

                    <div className="p-2 rounded-lg bg-emerald-50/40 border border-emerald-100/60 text-[11px] text-emerald-900 leading-relaxed">
                      <span className="font-semibold block text-[10px] text-emerald-700 mb-0.5">Решение:</span>
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
