import React, { useState } from 'react';
import { CsatDistributionPoint } from '../../types/analytics';
import { Star, ShieldAlert, CheckCircle2, HelpCircle } from 'lucide-react';

interface CsatComparisonChartProps {
  distribution: CsatDistributionPoint[];
  rawCsat: number;
  adjustedCsat: number;
}

export const CsatComparisonChart: React.FC<CsatComparisonChartProps> = ({
  distribution,
  rawCsat,
  adjustedCsat,
}) => {
  const [selectedStar, setSelectedStar] = useState<number | null>(1);

  const maxCount = Math.max(...distribution.map((d) => d.rawCount), 100);

  const totalEvaluations = distribution.reduce((sum, d) => sum + d.rawCount, 0);
  const totalExcluded = distribution.reduce((sum, d) => sum + d.excludedCount, 0);

  return (
    <div className="bg-white border border-[#E5E7EB] p-5 shadow-xs space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#F3F4F6] pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="p-1 bg-[#FEF2F2] text-[#DC2626] inline-flex">
              <ShieldAlert className="size-4" />
            </span>
            <h3 className="text-sm font-bold text-[#111827]">
              Аудит справедливости оценок (Базовый CSAT vs Adjusted CSAT)
            </h3>
            <span className="px-2 py-0.5 bg-[#DCFCE7] text-[#15803D] text-[10px] font-bold">
              ADR-0006
            </span>
          </div>
          <p className="text-xs text-[#6B7280]">
            Нейросетевой арбитраж LLM-Judge: выявление жалоб на инфраструктурные сбои (КриптоПро, СМЭВ) и очистка KPI операторов
          </p>
        </div>

        {/* Big comparison badges */}
        <div className="flex items-center gap-4 bg-[#F8FAFC] border border-[#E2E8F0] px-4 py-2 shrink-0">
          <div className="text-center pr-3 border-r border-[#CBD5E1]">
            <span className="text-[10px] font-semibold text-[#64748B] block uppercase tracking-wider">
              Базовый (Сырой)
            </span>
            <span className="text-xl font-bold text-[#94A3B8] line-through">
              {rawCsat.toFixed(2)} ★
            </span>
          </div>

          <div className="text-center">
            <span className="text-[10px] font-bold text-[#004B87] block uppercase tracking-wider">
              Скорректированный
            </span>
            <div className="flex items-center justify-center gap-1 text-2xl font-extrabold text-[#16A34A] leading-none">
              <span>{adjustedCsat.toFixed(2)}</span>
              <Star className="size-5 fill-[#16A34A] text-[#16A34A]" />
            </div>
          </div>

          <div className="bg-[#DCFCE7] text-[#15803D] text-xs font-extrabold px-2 py-1 border border-[#BBF7D0]">
            +{(adjustedCsat - rawCsat).toFixed(2)} ★
          </div>
        </div>
      </div>

      {/* Grid: Bar distribution + Explanation card */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* Distribution Bars */}
        <div className="lg:col-span-7 space-y-2.5">
          <div className="flex items-center justify-between text-[11px] text-[#6B7280] mb-1">
            <span className="font-semibold text-[#374151]">
              Распределение клиентских оценок (всего {totalEvaluations} отзывов)
            </span>
            <span className="text-[#DC2626] font-semibold">
              Исключено {totalExcluded} сфальсифицированных сбоями оценок
            </span>
          </div>

          <div className="space-y-2">
            {distribution.map((d) => {
              const isSelected = selectedStar === d.stars;
              const percent = (d.rawCount / maxCount) * 100;
              const hasExcluded = d.excludedCount > 0;
              const excludedPercent = (d.excludedCount / maxCount) * 100;
              const validPercent = percent - excludedPercent;

              return (
                <div
                  key={d.stars}
                  onClick={() => setSelectedStar(d.stars)}
                  className={`p-2 border transition cursor-pointer ${
                    isSelected
                      ? 'border-[#004B87] bg-[#F0F7FF]'
                      : 'border-transparent hover:bg-[#F9FAFB]'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <div className="flex items-center gap-1.5 font-bold text-[#111827]">
                      <span>{d.stars}</span>
                      <Star className="size-3.5 fill-[#F59E0B] text-[#F59E0B]" />
                      <span className="font-normal text-[#6B7280]">
                        ({d.rawCount} оценок)
                      </span>
                    </div>

                    <div className="flex items-center gap-2 font-mono text-[11px]">
                      {hasExcluded ? (
                        <span className="text-[#DC2626] font-semibold">
                          -{d.excludedCount} сбой ЭЦП
                        </span>
                      ) : null}
                      <span className="font-bold text-[#111827]">
                        {d.adjustedCount} в KPI
                      </span>
                    </div>
                  </div>

                  {/* Stacked bar */}
                  <div className="w-full bg-[#E5E7EB] h-2.5 overflow-hidden flex">
                    {/* Valid reviews portion */}
                    <div
                      className="h-full bg-[#10B981] transition-all duration-500"
                      style={{ width: `${validPercent}%` }}
                      title={`Зачтено в рейтинг оператора: ${d.adjustedCount}`}
                    />
                    {/* Excluded system issues portion (hatched/red) */}
                    {hasExcluded && (
                      <div
                        className="h-full bg-[#EF4444] transition-all duration-500 relative"
                        style={{ width: `${excludedPercent}%` }}
                        title={`Исключено как инфраструктурный сбой: ${d.excludedCount}`}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center gap-4 text-[11px] text-[#6B7280] pt-1">
            <div className="flex items-center gap-1.5">
              <span className="size-2.5 bg-[#10B981] inline-block" />
              <span>Зачтено в рейтинг оператора</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="size-2.5 bg-[#EF4444] inline-block" />
              <span>Исключено LLM-Judge (сбои ЭЦП / Портала)</span>
            </div>
          </div>
        </div>

        {/* Audit explanation card */}
        <div className="lg:col-span-5 bg-[#F9FAFB] border border-[#E5E7EB] p-4 space-y-3">
          <div className="flex items-center gap-2 border-b border-[#E5E7EB] pb-2">
            <CheckCircle2 className="size-4 text-[#16A34A]" />
            <span className="text-xs font-bold text-[#111827] uppercase tracking-wider">
              Почему CSAT вырос с 3.42 до 4.78?
            </span>
          </div>

          <div className="text-xs text-[#374151] space-y-2 leading-relaxed">
            <p>
              Из <strong>22 единиц</strong>, поставленных поставщиками за отчетный период, <strong>20 оценок</strong> были обусловлены невозможностью подписать оферту из-за ошибки плагина КриптоПро <code>0x80090014</code> и обновления браузеров.
            </p>
            <p>
              Операторы предоставили точные регламентные инструкции за рекордные <strong>18 секунд</strong>, однако поставщики выплеснули негатив на сервис.
            </p>
            <div className="p-2.5 bg-white border border-[#CBD5E1] space-y-1">
              <div className="text-[11px] font-bold text-[#004B87] flex items-center gap-1">
                <HelpCircle className="size-3" />
                <span>Формула защиты оператора:</span>
              </div>
              <p className="text-[11px] text-[#475569] font-mono">
                Adjusted CSAT = AVG(score) WHERE root_cause != 'system_issue'
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
