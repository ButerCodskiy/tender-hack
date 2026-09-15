import React, { useEffect, useRef, useState } from 'react';
import {
  X,
  ExternalLink,
  BookOpen,
  FileText,
  Copy,
  Check,
  Layers,
  Sparkles,
} from 'lucide-react';
import { Citation } from '../../types/chat';

interface SourceViewerDrawerProps {
  isOpen: boolean;
  citation: Citation | null;
  onClose: () => void;
}

export const SourceViewerDrawer: React.FC<SourceViewerDrawerProps> = ({
  isOpen,
  citation,
  onClose,
}) => {
  const [isCopied, setIsCopied] = useState(false);
  const markRef = useRef<HTMLElement | null>(null);

  // Закрытие по клавише Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Плавный скролл к подсвеченному фрагменту при открытии
  useEffect(() => {
    if (isOpen && markRef.current) {
      const timer = setTimeout(() => {
        markRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      }, 250);
      return () => clearTimeout(timer);
    }
  }, [isOpen, citation]);

  if (!isOpen || !citation) return null;

  const handleCopy = () => {
    const textToCopy =
      citation.parentFullContent || citation.excerpt || citation.title;
    navigator.clipboard.writeText(textToCopy);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const fullContent =
    citation.parentFullContent ||
    citation.excerpt ||
    'Текст документа недоступен.';
  const highlightQuote = citation.highlightQuote || citation.excerpt || '';

  // Рендеринг текста с подсветкой цитаты
  const renderHighlightedContent = () => {
    if (!highlightQuote || !fullContent.includes(highlightQuote)) {
      return (
        <div className="whitespace-pre-wrap leading-relaxed text-sm text-[#2d3748] dark:text-gray-200">
          {fullContent}
        </div>
      );
    }

    const parts = fullContent.split(highlightQuote);
    return (
      <div className="whitespace-pre-wrap leading-relaxed text-sm text-[#2d3748] dark:text-gray-200">
        {parts.map((part, index) => (
          <React.Fragment key={index}>
            {part}
            {index < parts.length - 1 && (
              <mark
                ref={index === 0 ? markRef : undefined}
                className="bg-amber-100 dark:bg-amber-900/60 text-amber-950 dark:text-amber-100 font-semibold px-1 py-0.5 rounded border border-amber-300 dark:border-amber-700/60 shadow-sm inline"
              >
                {highlightQuote}
              </mark>
            )}
          </React.Fragment>
        ))}
      </div>
    );
  };

  return (
    <>
      {/* Затемненный фон / Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/40 backdrop-blur-[2px] z-50 transition-opacity duration-300 animate-fade-in"
      />

      {/* Выдвижная шторка справа */}
      <aside
        aria-label="Просмотр нормативного документа"
        className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-white dark:bg-[#1a202c] shadow-2xl border-l border-[#e2e8f0] dark:border-gray-700 flex flex-col transform transition-transform duration-300 ease-out animate-slide-in-right"
      >
        {/* Шапка шторки */}
        <div className="px-6 py-4 border-b border-[#e2e8f0] dark:border-gray-700 bg-[#f8fafc] dark:bg-[#171923] flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            {/* Хлебные крошки / Section Path */}
            {citation.sectionPath && (
              <div className="flex items-center gap-1.5 text-xs text-[#718096] dark:text-gray-400 mb-1.5 font-medium truncate">
                <Layers className="size-3.5 text-[#4a5568] dark:text-gray-400 shrink-0" />
                <span>{citation.sectionPath}</span>
              </div>
            )}

            {/* Заголовок */}
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[#1a202c] dark:text-white truncate">
                {citation.parentTitle || citation.title}
              </h2>
            </div>

            {/* Статус / Тег: Полная статья vs Чанк */}
            <div className="flex items-center gap-2 mt-2">
              {citation.isParent ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800">
                  <BookOpen className="size-3" />
                  Родительская статья (Small-to-Big)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
                  <FileText className="size-3" />
                  Атомарный фрагмент
                </span>
              )}

              {highlightQuote && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                  <Sparkles className="size-3 text-amber-500" />
                  Точное попадание подсвечено
                </span>
              )}
            </div>
          </div>

          {/* Кнопки управления */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={handleCopy}
              title="Копировать текст статьи"
              className="p-2 rounded-lg text-[#718096] hover:text-[#1a202c] hover:bg-[#edf2f7] dark:hover:bg-gray-800 dark:text-gray-300 transition cursor-pointer"
            >
              {isCopied ? (
                <Check className="size-4 text-emerald-600" />
              ) : (
                <Copy className="size-4" />
              )}
            </button>

            {citation.url && (
              <a
                href={citation.url}
                target="_blank"
                rel="noreferrer"
                title="Перейти к нормативному первоисточнику"
                className="p-2 rounded-lg text-[#718096] hover:text-[#2b6cb0] hover:bg-[#ebf8ff] dark:hover:bg-gray-800 dark:text-gray-300 transition cursor-pointer"
              >
                <ExternalLink className="size-4" />
              </a>
            )}

            <button
              type="button"
              onClick={onClose}
              title="Закрыть (Esc)"
              className="p-2 rounded-lg text-[#718096] hover:text-[#e53e3e] hover:bg-[#fff5f5] dark:hover:bg-gray-800 dark:text-gray-300 transition cursor-pointer"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        {/* Тело документа со скроллом */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 font-sans selection:bg-amber-200 dark:selection:bg-amber-900">
          {/* Плашка найденной цитаты */}
          {highlightQuote && (
            <div className="p-3.5 bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-800/50 rounded-xl text-xs text-amber-900 dark:text-amber-200 flex items-start gap-2.5">
              <Sparkles className="size-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <span className="font-semibold block mb-0.5">
                  Фрагмент, подтверждающий ответ ассистента:
                </span>
                <p className="italic leading-relaxed line-clamp-3">
                  «{highlightQuote}»
                </p>
              </div>
            </div>
          )}

          {/* Полный текст статьи с визуальным фокусом */}
          <div className="p-5 bg-white dark:bg-[#1a202c] rounded-xl border border-[#e2e8f0] dark:border-gray-700 shadow-sm">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[#a0aec0] mb-3">
              Полный текст нормативного акта
            </h3>
            {renderHighlightedContent()}
          </div>
        </div>

        {/* Футер шторки с кнопкой первоисточника */}
        <div className="px-6 py-3.5 border-t border-[#e2e8f0] dark:border-gray-700 bg-[#f8fafc] dark:bg-[#171923] flex items-center justify-between text-xs text-[#718096] dark:text-gray-400">
          <span>ID узла: {citation.id}</span>
          {citation.url ? (
            <a
              href={citation.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-semibold text-[#2b6cb0] dark:text-sky-400 hover:underline cursor-pointer"
            >
              <span>Официальный первоисточник на zakupki.mos.ru</span>
              <ExternalLink className="size-3" />
            </a>
          ) : (
            <span className="text-[11px] text-[#a0aec0]">
              Нормативная база знаний ЕАИСТ
            </span>
          )}
        </div>
      </aside>
    </>
  );
};
