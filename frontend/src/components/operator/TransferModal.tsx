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
    color: 'text-[#264b82] bg-[#eaf6ff] border-[#b9dbf7]',
  },
  {
    code: 'L2',
    name: 'Линия 2 — Технические инциденты',
    description: 'Сбои ЭЦП, КриптоПро, интеграции с ЕИС/ФНС, ошибки сервера',
    icon: Wrench,
    color: 'text-[#b45309] bg-[#fef3c7] border-[#fde68a]',
  },
  {
    code: 'L3',
    name: 'Линия 3 — Юридический арбитраж',
    description: 'Разногласия по протоколам, жалобы УФАС, срыв сроков контракта',
    icon: Scale,
    color: 'text-[#6b21a8] bg-[#f3e8ff] border-[#e9d5ff]',
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
      <div className="w-full max-w-lg bg-white rounded-none border border-[#22242626] shadow-xl p-6 overflow-hidden">
        <div className="flex items-center justify-between pb-4 border-b border-[#e5e5e5]">
          <div className="flex items-center gap-2.5">
            <div className="size-8 rounded-none bg-[#eaf6ff] text-[#264b82] flex items-center justify-center">
              <ArrowRightLeft className="size-4.5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#1a1a1a]">Перевод обращения на другую линию</h3>
              <p className="text-xs text-[#666666]">Выберите профильную линию и укажите комментарий для коллег</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="size-7 rounded-none flex items-center justify-center text-[#666666] hover:text-[#1a1a1a] hover:bg-[#f7f8f9] transition cursor-pointer"
          >
            <X className="size-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="space-y-2">
            <label className="block text-[11px] font-bold uppercase tracking-wider text-[#666666]">
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
                    className={`flex items-start gap-3 p-3 rounded-none border transition-all cursor-pointer ${
                      isSelected
                        ? 'border-[#264b82] bg-[#eaf6ff]'
                        : isCurrent
                        ? 'border-[#e5e5e5] bg-[#f7f8f9] opacity-60'
                        : 'border-[#d4d4d5] hover:border-[#264b82] bg-white'
                    }`}
                  >
                    <input
                      type="radio"
                      name="target_line"
                      value={line.code}
                      checked={isSelected}
                      disabled={isCurrent}
                      onChange={(e) => setSelectedLine(e.target.value)}
                      className="mt-1 size-4 accent-[#264b82] text-[#264b82] focus:ring-[#264b82]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`size-5 rounded-none flex items-center justify-center text-xs font-bold border ${line.color}`}>
                          <Icon className="size-3" />
                        </span>
                        <span className="text-xs font-bold text-[#1a1a1a]">
                          {line.name} {isCurrent && '(Текущая)'}
                        </span>
                      </div>
                      <p className="text-[11px] text-[#666666] mt-1 leading-normal">
                        {line.description}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="block text-[11px] font-bold uppercase tracking-wider text-[#666666]">
              Комментарий оператора (причина перевода)
            </label>
            <textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Например: Ошибка валидации плагина КриптоПро 0x80090014, требуется помощь инженера L2..."
              className="w-full text-xs rounded-none border border-[#d4d4d5] bg-white p-3 focus:outline-hidden focus:border-[#264b82] transition resize-none text-[#1a1a1a]"
            />
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-[#e5e5e5]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-none border border-[#d4d4d5] text-xs font-semibold text-[#1a1a1a] hover:bg-[#f7f8f9] transition cursor-pointer"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting || selectedLine === currentLineCode}
              className="flex items-center gap-1.5 px-4 py-2 rounded-none bg-[#db2b21] hover:bg-[#b8231a] disabled:opacity-50 text-white text-xs font-bold transition cursor-pointer"
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
