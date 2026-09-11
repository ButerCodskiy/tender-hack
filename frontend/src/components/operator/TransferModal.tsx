import React, { useState } from 'react';
import { X, ArrowRightLeft, ShieldAlert, Wrench, Scale } from 'lucide-react';

interface TransferModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (targetLineCode: string, comment: string) => void;
  currentLineCode?: string;
}

const SUPPORT_LINES = [
  {
    code: 'L1',
    name: 'Линия 1 — Первичная поддержка',
    description: 'Общие регламенты 44/223-ФЗ, навигация, регистрация',
    icon: ShieldAlert,
    color: 'text-primary-600 bg-primary-50 border-primary-200',
  },
  {
    code: 'L2',
    name: 'Линия 2 — Технические инциденты',
    description: 'Сбои ЭЦП, КриптоПро, интеграции с ЕИС/ФНС, ошибки сервера',
    icon: Wrench,
    color: 'text-amber-600 bg-amber-50 border-amber-200',
  },
  {
    code: 'L3',
    name: 'Линия 3 — Юридический арбитраж',
    description: 'Разногласия по протоколам, жалобы УФАС, срыв сроков контракта',
    icon: Scale,
    color: 'text-purple-600 bg-purple-50 border-purple-200',
  },
];

export const TransferModal: React.FC<TransferModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  currentLineCode = 'L1',
}) => {
  const [selectedLine, setSelectedLine] = useState<string>(
    currentLineCode === 'L1' ? 'L2' : 'L1'
  );
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onConfirm(selectedLine, comment.trim());
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-white rounded-3xl border border-gray-100 shadow-2xl p-6 overflow-hidden">
        <div className="flex items-center justify-between pb-4 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="size-9 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center">
              <ArrowRightLeft className="size-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-title-50">Перевод обращения на другую линию</h3>
              <p className="text-xs text-text-100">Выберите профильную линию и укажите комментарий для коллег</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="size-8 rounded-xl flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition cursor-pointer"
          >
            <X className="size-4.5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400">
              Целевая линия поддержки
            </label>
            <div className="space-y-2">
              {SUPPORT_LINES.map((line) => {
                const Icon = line.icon;
                const isCurrent = line.code === currentLineCode;
                const isSelected = selectedLine === line.code;

                return (
                  <label
                    key={line.code}
                    className={`flex items-start gap-3 p-3 rounded-2xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50/40 shadow-xs ring-1 ring-primary-500'
                        : isCurrent
                        ? 'border-gray-100 bg-gray-50/50 opacity-60'
                        : 'border-gray-200/80 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <input
                      type="radio"
                      name="target_line"
                      value={line.code}
                      checked={isSelected}
                      disabled={isCurrent}
                      onChange={(e) => setSelectedLine(e.target.value)}
                      className="mt-1 size-4 text-primary-600 focus:ring-primary-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`size-5 rounded-md flex items-center justify-center text-xs font-bold border ${line.color}`}>
                          <Icon className="size-3" />
                        </span>
                        <span className="text-xs font-bold text-title-50">
                          {line.name} {isCurrent && '(Текущая)'}
                        </span>
                      </div>
                      <p className="text-[11px] text-text-100 mt-1 leading-normal">
                        {line.description}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400">
              Комментарий оператора (причина перевода)
            </label>
            <textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Например: Ошибка валидации плагина КриптоПро 0x80090014, требуется помощь инженера L2..."
              className="w-full text-xs md:text-sm rounded-2xl border border-gray-200 bg-gray-50/50 p-3 focus:bg-white focus:outline-hidden focus:border-primary-500 focus:ring-2 focus:ring-primary-100 transition resize-none"
            />
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-gray-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-text-100 hover:bg-gray-100 transition cursor-pointer"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting || selectedLine === currentLineCode}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition cursor-pointer"
            >
              <ArrowRightLeft className="size-3.5" />
              <span>{isSubmitting ? 'Перевод...' : 'Перевести обращение'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
