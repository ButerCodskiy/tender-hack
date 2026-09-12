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
        className={`relative flex flex-col bg-white rounded-none transition-all duration-150 border ${
          isFocused
            ? 'border-[#264b82] ring-1 ring-[#264b82]'
            : 'border-[#d4d4d5] hover:border-[#264b82]'
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
          placeholder="Задайте вопрос по регламенту, офертам, закупкам..."
          className="w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-[14px] text-[#1a1a1a] placeholder:text-[#7f8792] focus:outline-none custom-scrollbar leading-relaxed"
        />

        {/* Action Toolbar */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-1.5 border-t border-[#e5e5e5] bg-[#fafafa]">
          <div className="flex items-center gap-1">
            {/* Attachment Button */}
            <label
              title="Прикрепить регламент или файл"
              className="size-8 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
            >
              <Paperclip className="size-4" />
              <input type="file" className="hidden" />
            </label>
          </div>

          <div className="flex items-center gap-2">
            {/* Send Message Button: Mos Red CTA */}
            <button
              type="button"
              disabled={!inputValue.trim() || isSending}
              onClick={onSend}
              aria-label="Отправить сообщение"
              className={`size-8 rounded-none flex items-center justify-center transition-colors cursor-pointer ${
                inputValue.trim() && !isSending
                  ? 'bg-[#db2b21] hover:bg-[#cd1f15] active:bg-[#af221a] text-white'
                  : 'bg-[#eeeeee] text-[#9ba1a9] cursor-not-allowed'
              }`}
            >
              <ArrowUp className="size-4.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
