import React, { useState } from 'react';
import { Star, X, CheckCircle2 } from 'lucide-react';

interface CsatModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (score: number, comment: string, reasonCategory: string) => void;
}

export const CsatModal: React.FC<CsatModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [reasonCategory, setReasonCategory] = useState('resolved_well');
  const [isSubmitted, setIsSubmitted] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(rating, comment, reasonCategory);
    setIsSubmitted(true);
    setTimeout(() => {
      setIsSubmitted(false);
      onClose();
    }, 1500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative w-full max-w-md bg-white rounded-none p-6 shadow-xl border border-[#22242626]">
        <button
          onClick={onClose}
          className="absolute right-3 top-3 p-1.5 text-[#7f8792] hover:text-[#1a1a1a] rounded-none hover:bg-[#f2f7fc] transition cursor-pointer"
        >
          <X className="size-5" />
        </button>

        {isSubmitted ? (
          <div className="py-6 flex flex-col items-center text-center space-y-3">
            <div className="size-12 rounded-full bg-[#e7f8f2] text-[#0d9b68] flex items-center justify-center">
              <CheckCircle2 className="size-7" />
            </div>
            <h3 className="text-base font-bold text-[#1a1a1a]">Спасибо за оценку!</h3>
            <p className="text-xs text-[#7f8792] max-w-xs">
              Ваш отзыв помогает контролировать качество консультаций по регламентам ЕАИСТ.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="text-center">
              <h3 className="text-base font-bold text-[#1a1a1a] mb-1">
                Оцените качество консультации
              </h3>
              <p className="text-xs text-[#7f8792]">
                Помог ли ответ ИИ-ассистента решить ваш вопрос по регламенту?
              </p>
            </div>

            {/* Star Rating */}
            <div className="flex justify-center gap-2 py-1">
              {[1, 2, 3, 4, 5].map((star) => {
                const isFilled = (hoverRating || rating) >= star;
                return (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    onMouseEnter={() => setHoverRating(star)}
                    onMouseLeave={() => setHoverRating(null)}
                    className="p-1 text-[#dddddd] transition cursor-pointer"
                  >
                    <Star
                      className={`size-7 ${
                        isFilled ? 'text-[#fbbd08] fill-[#fbbd08]' : 'text-[#dddddd]'
                      }`}
                    />
                  </button>
                );
              })}
            </div>

            {/* Category selection for low scores */}
            {rating <= 3 && (
              <div className="space-y-1">
                <label className="text-xs font-bold text-[#1a1a1a] block">
                  Причина низкой оценки:
                </label>
                <select
                  value={reasonCategory}
                  onChange={(e) => setReasonCategory(e.target.value)}
                  className="w-full text-xs rounded-none border border-[#d4d4d5] bg-white px-3 py-2 text-[#1a1a1a] focus:outline-none focus:border-[#264b82] cursor-pointer"
                >
                  <option value="system_bug">Технический сбой / баг Портала</option>
                  <option value="unclear_answer">Ответ был неполным или непонятным</option>
                  <option value="law_disagreement">Несогласие с нормами 44-ФЗ / регламентом</option>
                </select>
              </div>
            )}

            {/* Text Comment */}
            <div>
              <label className="text-xs font-bold text-[#1a1a1a] block mb-1">
                Комментарий (необязательно)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Что можно улучшить в ответе или работе сервиса?"
                rows={3}
                className="w-full text-xs rounded-none border border-[#d4d4d5] p-2.5 text-[#1a1a1a] placeholder:text-[#7f8792] focus:outline-none focus:border-[#264b82] custom-scrollbar"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end gap-2 pt-1 border-t border-[#e5e5e5]">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-[#1a1a1a] border border-[#22242626] hover:bg-[#f2f7fc] rounded-none transition cursor-pointer"
              >
                Пропустить
              </button>
              <button
                type="submit"
                className="px-5 py-2 text-xs font-bold text-white bg-[#db2b21] hover:bg-[#cd1f15] rounded-none transition cursor-pointer"
              >
                Отправить оценку
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
