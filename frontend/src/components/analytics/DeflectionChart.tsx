import React, { useState } from 'react';
import { DeflectionTrendPoint, CategoryBreakdown } from '../../types/analytics';
import { Bot, TrendingUp, CheckCircle } from 'lucide-react';

interface DeflectionChartProps {
  trendData: DeflectionTrendPoint[];
  categories: CategoryBreakdown[];
  currentRate: number;
  botTickets: number;
  totalTickets: number;
}

export const DeflectionChart: React.FC<DeflectionChartProps> = ({
  trendData,
  categories,
  currentRate,
  botTickets,
  totalTickets,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // SVG Chart dimensions
  const width = 560;
  const height = 190;
  const padding = { top: 25, right: 25, bottom: 35, left: 40 };

  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const minRate = 40;
  const maxRate = 80;

  const points = trendData.map((d, i) => {
    const x = padding.left + (i / (trendData.length - 1)) * chartW;
    const y = padding.top + chartH - ((d.rate - minRate) / (maxRate - minRate)) * chartH;
    return { x, y, ...d };
  });

  const linePath = points.reduce((acc, pt, idx) => {
    return idx === 0 ? `M ${pt.x},${pt.y}` : `${acc} L ${pt.x},${pt.y}`;
  }, '');

  const areaPath = points.length > 0
    ? `${linePath} L ${points[points.length - 1].x},${padding.top + chartH} L ${points[0].x},${padding.top + chartH} Z`
    : '';

  return (
    <div className="bg-white border border-[#E5E7EB] p-5 shadow-xs space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#F3F4F6] pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="p-1 bg-[#EAF6FF] text-[#004B87] inline-flex">
              <Bot className="size-4" />
            </span>
            <h3 className="text-sm font-bold text-[#111827]">
              Автоматическое решение обращений (Deflection Rate)
            </h3>
            <span className="px-2 py-0.5 bg-[#DCFCE7] text-[#15803D] text-[10px] font-bold">
              Цель 65%+ выполнена
            </span>
          </div>
          <p className="text-xs text-[#6B7280]">
            Доля запросов, закрытых ИИ-ботом RAG на шаге первичной консультации без привлечения оператора
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[10px] text-[#6B7280] uppercase tracking-wider block font-semibold">
              Текущий показатель
            </span>
            <span className="text-2xl font-extrabold text-[#004B87] leading-none">
              {currentRate.toFixed(1)}%
            </span>
          </div>
          <div className="text-right border-l border-[#E5E7EB] pl-3">
            <span className="text-[10px] text-[#6B7280] uppercase tracking-wider block font-semibold">
              Закрыто ботом
            </span>
            <span className="text-sm font-bold text-[#111827]">
              {botTickets} <span className="text-xs text-[#6B7280] font-normal">/ {totalTickets}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Grid: SVG Trend Chart + Topic Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* SVG Area Chart */}
        <div className="lg:col-span-7 relative">
          <div className="flex items-center justify-between text-[11px] text-[#6B7280] mb-1">
            <span className="font-semibold text-[#374151] flex items-center gap-1">
              <TrendingUp className="size-3 text-[#16A34A]" /> Динамика за 7 дней (рост +19.8%)
            </span>
            <span>Норматив: &ge; 60%</span>
          </div>

          <div className="w-full overflow-x-auto">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="w-full h-auto select-none overflow-visible"
            >
              <defs>
                <linearGradient id="deflectionGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#004B87" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#004B87" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Grid lines */}
              {[40, 50, 60, 70, 80].map((val) => {
                const y = padding.top + chartH - ((val - minRate) / (maxRate - minRate)) * chartH;
                return (
                  <g key={val}>
                    <line
                      x1={padding.left}
                      y1={y}
                      x2={width - padding.right}
                      y2={y}
                      stroke={val === 60 ? '#10B981' : '#E5E7EB'}
                      strokeDasharray={val === 60 ? '4 3' : undefined}
                      strokeWidth={val === 60 ? '1.5' : '1'}
                    />
                    <text
                      x={padding.left - 6}
                      y={y + 3.5}
                      textAnchor="end"
                      fontSize="9"
                      fill={val === 60 ? '#059669' : '#9CA3AF'}
                      fontFamily="monospace"
                      fontWeight={val === 60 ? 'bold' : 'normal'}
                    >
                      {val}%
                    </text>
                  </g>
                );
              })}

              {/* Area fill */}
              <path d={areaPath} fill="url(#deflectionGrad)" />

              {/* Line path */}
              <path
                d={linePath}
                fill="none"
                stroke="#004B87"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />

              {/* Data points */}
              {points.map((pt, i) => {
                const isHovered = hoveredIdx === i;
                const isLast = i === points.length - 1;
                return (
                  <g
                    key={pt.dayLabel}
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? 6 : isLast ? 5 : 3.5}
                      fill={isLast ? '#E31E24' : '#004B87'}
                      stroke="#FFFFFF"
                      strokeWidth="2"
                    />
                    <text
                      x={pt.x}
                      y={height - 12}
                      textAnchor="middle"
                      fontSize="10"
                      fill="#6B7280"
                      fontWeight={isLast ? 'bold' : 'normal'}
                    >
                      {pt.dayLabel}
                    </text>
                    {/* Tooltip badge */}
                    {(isHovered || isLast) && (
                      <g transform={`translate(${pt.x}, ${pt.y - 14})`}>
                        <rect
                          x="-22"
                          y="-16"
                          width="44"
                          height="16"
                          rx="2"
                          fill={isLast ? '#004B87' : '#1F2937'}
                        />
                        <text
                          x="0"
                          y="-4"
                          textAnchor="middle"
                          fontSize="9"
                          fill="#FFFFFF"
                          fontWeight="bold"
                        >
                          {pt.rate.toFixed(1)}%
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Topic Breakdown Bars */}
        <div className="lg:col-span-5 bg-[#F9FAFB] border border-[#E5E7EB] p-3.5 space-y-2.5">
          <div className="flex items-center justify-between border-b border-[#E5E7EB] pb-1.5">
            <span className="text-xs font-bold text-[#111827] uppercase tracking-wider">
              Структура тем консультаций
            </span>
            <span className="text-[10px] text-[#6B7280]">Доля в общем объеме</span>
          </div>

          <div className="space-y-2">
            {categories.map((cat) => (
              <div key={cat.label} className="space-y-1 text-xs">
                <div className="flex items-center justify-between text-[#374151]">
                  <span className="truncate pr-2 font-medium">{cat.label}</span>
                  <div className="flex items-center gap-1.5 font-mono text-[11px] shrink-0">
                    <span className="font-bold text-[#111827]">{cat.count}</span>
                    <span className="text-[#6B7280]">({cat.share}%)</span>
                  </div>
                </div>
                <div className="w-full bg-[#E5E7EB] h-1.5 overflow-hidden">
                  <div
                    className="h-full transition-all duration-500"
                    style={{
                      width: `${cat.share}%`,
                      backgroundColor: cat.color,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-[#E5E7EB] flex items-center justify-between text-[11px] text-[#059669] font-medium">
            <span className="inline-flex items-center gap-1">
              <CheckCircle className="size-3 text-[#10B981]" /> База знаний покрывает 94.2% типовых запросов
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
