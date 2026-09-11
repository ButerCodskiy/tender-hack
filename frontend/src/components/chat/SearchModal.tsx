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
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-xs pt-20 p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl bg-white rounded-3xl p-4 shadow-2xl border border-gray-100 animate-in zoom-in-95 duration-200">
        {/* Search Input */}
        <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-100">
          <Search className="size-5 text-gray-400" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по истории вопросов и ответов..."
            className="w-full text-sm text-title-50 placeholder:text-gray-400 focus:outline-none bg-transparent"
          />
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 transition cursor-pointer"
          >
            <X className="size-4.5" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto custom-scrollbar py-2 space-y-1">
          {filteredSessions.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-400">
              {query.trim() ? 'Ничего не найдено' : 'Введите запрос для поиска'}
            </div>
          ) : (
            filteredSessions.map((session) => (
              <button
                key={session.id}
                onClick={() => {
                  onSelectSession(session.id);
                  onClose();
                }}
                className="w-full flex items-center justify-between p-3 rounded-2xl hover:bg-gray-50 text-left transition cursor-pointer group"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="size-8 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center shrink-0">
                    <MessageSquare className="size-4" />
                  </div>
                  <div className="truncate">
                    <span className="text-sm font-medium text-title-50 block truncate group-hover:text-primary-600 transition-colors">
                      {session.title}
                    </span>
                    <span className="text-xs text-text-100 block truncate">
                      {session.messages.length} сообщ. · {session.createdAt}
                    </span>
                  </div>
                </div>
                <ArrowRight className="size-4 text-gray-300 group-hover:text-primary-500 group-hover:translate-x-0.5 transition-all shrink-0" />
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
