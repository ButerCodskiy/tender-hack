import React from 'react';
import {
  Search,
  KeyRound,
  Briefcase,
  Scale,
  Sparkles,
} from 'lucide-react';
import { ChatComposer } from './ChatComposer';
import { QuickPrompt } from '../../types/chat';

interface WelcomeScreenProps {
  inputValue: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  isSending?: boolean;
  onSelectQuickPrompt: (prompt: string) => void;
}

const QUICK_PROMPTS: QuickPrompt[] = [
  {
    id: 1,
    label: 'Регистрация и ЕСИА',
    prompt: 'Как зарегистрироваться на Портале поставщиков через ЕСИА?',
    category: 'Регистрация',
  },
  {
    id: 2,
    label: 'Требования к ЭЦП и МЧД',
    prompt: 'Какая электронная подпись нужна для участия в закупках и как настроить МЧД?',
    category: 'ЭЦП',
  },
  {
    id: 3,
    label: 'Котировочные сессии',
    prompt: 'Как принять участие в котировочной сессии и подать ценовое предложение?',
    category: 'Закупки',
  },
  {
    id: 4,
    label: 'Обжалование и споры',
    prompt: 'Какой регламент подачи претензий заказчику и жалоб в УФАС?',
    category: 'Споры',
  },
];

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  inputValue,
  onInputChange,
  onSend,
  isSending = false,
  onSelectQuickPrompt,
}) => {
  const getPromptIcon = (id: number) => {
    switch (id) {
      case 1:
        return <Search className="size-4 text-[#264b82]" />;
      case 2:
        return <KeyRound className="size-4 text-[#264b82]" />;
      case 3:
        return <Briefcase className="size-4 text-[#264b82]" />;
      case 4:
        return <Scale className="size-4 text-[#264b82]" />;
      default:
        return <Sparkles className="size-4 text-[#db2b21]" />;
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 md:p-12 overflow-y-auto custom-scrollbar select-none bg-[#f7f8f9]">
      <div className="w-full max-w-3xl flex flex-col items-center">
        {/* B2G Headline */}
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-center mb-2 text-[#1a1a1a]">
          Чем служба поддержки может помочь?
        </h1>

        {/* Subtitle */}
        <p className="text-[#7f8792] text-sm md:text-base text-center max-w-lg mb-8 leading-relaxed font-normal">
          Интеллектуальный ассистент найдет точные регламенты ЕАИСТ, разъяснит правила участия в закупках и свяжет со специалистом.
        </p>

        {/* Centered Composer */}
        <div className="w-full mb-8">
          <ChatComposer
            variant="centered"
            inputValue={inputValue}
            onInputChange={onInputChange}
            onSend={onSend}
            isSending={isSending}
          />
        </div>

        {/* Quick Action Chips: Rectangular official buttons */}
        <div className="flex flex-wrap items-center justify-center gap-2 max-w-2xl">
          {QUICK_PROMPTS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectQuickPrompt(item.prompt)}
              className="flex items-center gap-2 px-4 py-2 rounded-none border border-[#22242626] bg-white hover:bg-[#f2f7fc] hover:border-[#264b82] text-xs md:text-sm font-semibold text-[#1a1a1a] transition-all cursor-pointer"
            >
              {getPromptIcon(item.id)}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
