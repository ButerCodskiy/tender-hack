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
        return <Search className="size-4 text-primary-500" />;
      case 2:
        return <KeyRound className="size-4 text-primary-500" />;
      case 3:
        return <Briefcase className="size-4 text-primary-500" />;
      case 4:
        return <Scale className="size-4 text-primary-500" />;
      default:
        return <Sparkles className="size-4 text-primary-500" />;
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 md:p-12 overflow-y-auto custom-scrollbar select-none">
      <div className="w-full max-w-3xl flex flex-col items-center">
        {/* Header Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-50 border border-primary-100 text-primary-600 text-xs font-medium mb-4 shadow-2xs">
          <Sparkles className="size-3.5" />
          <span>База знаний Портала поставщиков</span>
        </div>

        {/* Gradient Headline */}
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-center mb-3 bg-gradient-to-r from-primary-500 via-primary-400 to-primary-300 bg-clip-text text-transparent">
          Чем я могу помочь?
        </h1>

        {/* Subtitle */}
        <p className="text-text-100 text-sm md:text-base text-center max-w-lg mb-8 leading-relaxed font-normal">
          Интеллектуальный ассистент найдет точные регламенты, разъяснит правила участия в закупках и свяжет со специалистом.
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

        {/* Quick Action Chips matching TailGrids design */}
        <div className="flex flex-wrap items-center justify-center gap-2.5 max-w-2xl">
          {QUICK_PROMPTS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectQuickPrompt(item.prompt)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-full border border-gray-200/80 bg-white hover:bg-gray-50 hover:border-gray-300 text-xs md:text-sm font-medium text-gray-700 shadow-2xs transition-all active:scale-[0.98] cursor-pointer"
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
