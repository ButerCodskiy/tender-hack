import React, { useState } from 'react';
import { Search, X, MessageSquare, ArrowRight } from 'lucide-react';
import { ChatSession } from '../../types/chat';

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessions: ChatSession[];
  onSelectSession: (id: string) => void;
}

export const SearchModal: React.FC<SearchModalProps> = ({
  isOpen,
  onClose,
  sessions,
  onSelectSession,
}) => {
  const [query, setQuery] = useState('');

  if (!isOpen) return null;

  const filteredSessions = sessions.filter((s) => {
    const inTitle = s.title.toLowerCase().includes(query.toLowerCase());
    const inMessages = s.messages.some((m) =>
      m.content.toLowerCase().includes(query.toLowerCase())
    );
    return inTitle || inMessages;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16 p-4">
      <div className="relative w-full max-w-xl bg-white rounded-none p-4 shadow-xl border border-[#22242626]">
        {/* Search Input */}
        <div className="flex items-center gap-3 px-3 py-2 border-b border-[#dddddd]">
          <Search className="size-4.5 text-[#7f8792]" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по истории вопросов и ответов..."
            className="w-full text-[14px] text-[#1a1a1a] placeholder:text-[#7f8792] focus:outline-none bg-transparent"
          />
          <button
            onClick={onClose}
            className="p-1 rounded-none text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
          >
            <X className="size-4.5" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto custom-scrollbar py-2 space-y-0.5">
          {filteredSessions.length === 0 ? (
            <div className="py-8 text-center text-xs text-[#7f8792]">
              {query.trim() ? 'Ничего не найдено' : 'Введите запрос для поиска по диалогам'}
            </div>
          ) : (
            filteredSessions.map((session) => (
              <button
                key={session.id}
                onClick={() => {
                  onSelectSession(session.id);
                  onClose();
                }}
                className="w-full flex items-center justify-between p-2.5 rounded-none hover:bg-[#f2f7fc] text-left transition cursor-pointer group border-b border-[#e5e5e5]"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="size-8 rounded-none bg-[#fef0ef] text-[#db2b21] border border-[#db2b21]/20 flex items-center justify-center shrink-0">
                    <MessageSquare className="size-4" />
                  </div>
                  <div className="truncate">
                    <span className="text-xs font-bold text-[#1a1a1a] block truncate group-hover:text-[#264b82] transition-colors">
                      {session.title}
                    </span>
                    <span className="text-[11px] text-[#7f8792] block truncate">
                      {session.messages.length} сообщ. · {session.createdAt}
                    </span>
                  </div>
                </div>
                <ArrowRight className="size-4 text-[#7f8792] group-hover:text-[#264b82] group-hover:translate-x-0.5 transition-all shrink-0" />
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
