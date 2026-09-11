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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl border border-gray-100 animate-in zoom-in-95 duration-200">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 p-2 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100 transition cursor-pointer"
        >
          <X className="size-5" />
        </button>

        {isSubmitted ? (
          <div className="py-8 flex flex-col items-center text-center space-y-3">
            <div className="size-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 className="size-7" />
            </div>
            <h3 className="text-lg font-semibold text-title-50">Спасибо за оценку!</h3>
            <p className="text-xs text-text-100 max-w-xs">
              Ваш отзыв помогает обучать ИИ-ассистента и улучшать качество консультаций.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="text-center">
              <h3 className="text-lg font-semibold text-title-50 mb-1">
                Оцените качество консультации
              </h3>
              <p className="text-xs text-text-100">
                Помог ли ответ ИИ-ассистента решить ваш вопрос?
              </p>
            </div>

            {/* Star Rating */}
            <div className="flex justify-center gap-2 py-2">
              {[1, 2, 3, 4, 5].map((star) => {
                const isFilled = (hoverRating || rating) >= star;
                return (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    onMouseEnter={() => setHoverRating(star)}
                    onMouseLeave={() => setHoverRating(null)}
                    className="p-1 text-gray-300 hover:scale-110 transition cursor-pointer"
                  >
                    <Star
                      className={`size-8 ${
                        isFilled ? 'text-amber-400 fill-amber-400' : 'text-gray-200'
                      }`}
                    />
                  </button>
                );
              })}
            </div>

            {/* Category selection for low scores */}
            {rating <= 3 && (
              <div className="space-y-1.5 animate-in fade-in duration-200">
                <label className="text-xs font-semibold text-gray-700 block">
                  Причина низкой оценки (для справедливого ИИ-арбитража):
                </label>
                <select
                  value={reasonCategory}
                  onChange={(e) => setReasonCategory(e.target.value)}
                  className="w-full text-xs rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-gray-800 focus:outline-none focus:border-primary-500 cursor-pointer"
                >
                  <option value="system_bug">Технический сбой / баг Портала</option>
                  <option value="unclear_answer">Ответ был неполным или непонятным</option>
                  <option value="law_disagreement">Несогласие с нормами 44-ФЗ / регламентом</option>
                </select>
              </div>
            )}

            {/* Text Comment */}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">
                Комментарий (необязательно)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Что можно улучшить в ответе или работе сервиса?"
                rows={3}
                className="w-full text-xs rounded-xl border border-gray-200 p-3 text-title-50 placeholder:text-gray-400 focus:outline-none focus:border-primary-500 custom-scrollbar"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded-xl transition cursor-pointer"
              >
                Пропустить
              </button>
              <button
                type="submit"
                className="px-5 py-2 text-xs font-semibold text-white bg-primary-500 hover:bg-primary-600 rounded-xl shadow-xs transition cursor-pointer active:scale-95"
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
