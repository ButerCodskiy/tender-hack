import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Paperclip } from 'lucide-react';

interface ChatComposerProps {
  inputValue: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  isSending?: boolean;
  variant?: 'centered' | 'bottom';
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  inputValue,
  onInputChange,
  onSend,
  isSending = false,
  variant = 'centered',
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      const newHeight = Math.max(56, Math.min(el.scrollHeight, 200));
      el.style.height = `${newHeight}px`;
      el.style.overflowY = el.scrollHeight > 200 ? 'scroll' : 'hidden';
    }
  }, [inputValue]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (inputValue.trim() && !isSending) {
        onSend();
      }
    }
  };

  return (
    <div
      className={`w-full transition-all duration-200 ${
        variant === 'centered' ? 'max-w-3xl mx-auto' : 'max-w-4xl mx-auto'
      }`}
    >
      <div
        className={`relative flex flex-col bg-white rounded-3xl transition-all duration-200 border ${
          isFocused
            ? 'border-primary-500 shadow-lg shadow-primary-500/10'
            : 'border-gray-200 shadow-[0_12px_24px_-8px_rgba(0,0,0,0.06)] hover:border-gray-300'
        }`}
      >
        {/* Text Area Input */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={inputValue}
          disabled={isSending}
          onChange={(e) => onInputChange(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder="Задайте вопрос по закупкам, регламентам, офертам..."
          className="w-full resize-none bg-transparent px-5 pt-4 pb-2 text-base text-title-50 placeholder:text-gray-400 focus:outline-none custom-scrollbar leading-relaxed"
        />

        {/* Action Toolbar */}
        <div className="flex items-center justify-between px-3 pb-3 pt-1 border-t border-gray-50/80">
          <div className="flex items-center gap-1">
            {/* Attachment Button */}
            <label
              title="Прикрепить регламент или файл"
              className="size-8 rounded-full flex items-center justify-center text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition cursor-pointer"
            >
              <Paperclip className="size-4" />
              <input type="file" className="hidden" />
            </label>
          </div>

          <div className="flex items-center gap-2">
            {/* Send Message Button */}
            <button
              type="button"
              disabled={!inputValue.trim() || isSending}
              onClick={onSend}
              aria-label="Отправить сообщение"
              className={`size-9 rounded-full flex items-center justify-center transition-all cursor-pointer ${
                inputValue.trim() && !isSending
                  ? 'bg-primary-500 text-white shadow-sm shadow-primary-500/30 hover:bg-primary-600 active:scale-95'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed opacity-60'
              }`}
            >
              <ArrowUp className="size-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
