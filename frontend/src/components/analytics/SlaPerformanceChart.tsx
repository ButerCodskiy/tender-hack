import React, { useState } from 'react';
import { SlaTimelinePoint } from '../../types/analytics';
import { Clock, Activity, ShieldCheck, CheckCircle2 } from 'lucide-react';

interface SlaPerformanceChartProps {
  timelineData: SlaTimelinePoint[];
  avgFrtSec: number;
  avgAhtSec: number;
}

export const SlaPerformanceChart: React.FC<SlaPerformanceChartProps> = ({
  timelineData,
  avgFrtSec,
  avgAhtSec,
}) => {
  const [activePoint, setActivePoint] = useState<number | null>(null);

  const width = 560;
  const height = 180;
  const padding = { top: 25, right: 25, bottom: 35, left: 40 };

  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const maxVal = 70; // 70 sec scale (SLA limit at 60s)

  const points = timelineData.map((d, i) => {
    const x = padding.left + (i / (timelineData.length - 1)) * chartW;
    const y = padding.top + chartH - (d.frtSec / maxVal) * chartH;
    return { x, y, ...d };
  });

  const linePath = points.reduce((acc, pt, idx) => {
    return idx === 0 ? `M ${pt.x},${pt.y}` : `${acc} L ${pt.x},${pt.y}`;
  }, '');

  const slaY = padding.top + chartH - (60 / maxVal) * chartH;

  const ahtMinutes = Math.floor(avgAhtSec / 60);
  const ahtSeconds = Math.round(avgAhtSec % 60);

  return (
    <div className="bg-white border border-[#E5E7EB] p-5 shadow-xs space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#F3F4F6] pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="p-1 bg-[#FEF3C7] text-[#D97706] inline-flex">
              <Clock className="size-4" />
            </span>
            <h3 className="text-sm font-bold text-[#111827]">
              Контроль соблюдения нормативов SLA (FRT / AHT)
            </h3>
            <span className="px-2 py-0.5 bg-[#DCFCE7] text-[#15803D] text-[10px] font-bold">
              SLA 98.4%
            </span>
          </div>
          <p className="text-xs text-[#6B7280]">
            Скорость первого реагирования (FRT &le; 60 с для P0) и среднее время полного решения инцидента
          </p>
        </div>

        {/* Big numbers */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="text-[10px] text-[#6B7280] uppercase tracking-wider block font-semibold">
              Время 1-го ответа (FRT)
            </span>
            <span className="text-2xl font-extrabold text-[#111827] leading-none">
              {Math.round(avgFrtSec)} <span className="text-sm font-normal text-[#6B7280]">сек</span>
            </span>
          </div>

          <div className="text-right border-l border-[#E5E7EB] pl-4">
            <span className="text-[10px] text-[#6B7280] uppercase tracking-wider block font-semibold">
              Время решения (AHT)
            </span>
            <span className="text-2xl font-extrabold text-[#7C3AED] leading-none">
              {ahtMinutes}.{Math.round((ahtSeconds / 60) * 10)} <span className="text-sm font-normal text-[#6B7280]">мин</span>
            </span>
          </div>
        </div>
      </div>

      {/* SVG Timeline Chart + Summary Badges */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* SVG FRT vs SLA */}
        <div className="lg:col-span-8 relative">
          <div className="flex items-center justify-between text-[11px] text-[#6B7280] mb-1">
            <span className="font-semibold text-[#374151]">
              Почасовой мониторинг первого ответа оператора / бота
            </span>
            <span className="text-[#DC2626] font-semibold flex items-center gap-1">
              <span className="inline-block w-3 h-0.5 bg-[#DC2626] border-b border-dashed" />
              Лимит SLA: 60 сек
            </span>
          </div>

          <div className="w-full overflow-x-auto">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="w-full h-auto select-none overflow-visible"
            >
              {/* Safe zone green fill below 60s */}
              <rect
                x={padding.left}
                y={slaY}
                width={chartW}
                height={chartH - (slaY - padding.top)}
                fill="#F0FDF4"
                opacity="0.6"
              />

              {/* Grid lines */}
              {[20, 40, 60].map((val) => {
                const y = padding.top + chartH - (val / maxVal) * chartH;
                const isSla = val === 60;
                return (
                  <g key={val}>
                    <line
                      x1={padding.left}
                      y1={y}
                      x2={width - padding.right}
                      y2={y}
                      stroke={isSla ? '#DC2626' : '#E5E7EB'}
                      strokeDasharray={isSla ? '5 3' : undefined}
                      strokeWidth={isSla ? '1.5' : '1'}
                    />
                    <text
                      x={padding.left - 6}
                      y={y + 3.5}
                      textAnchor="end"
                      fontSize="9"
                      fill={isSla ? '#DC2626' : '#9CA3AF'}
                      fontFamily="monospace"
                      fontWeight={isSla ? 'bold' : 'normal'}
                    >
                      {val}с
                    </text>
                  </g>
                );
              })}

              {/* Line */}
              <path
                d={linePath}
                fill="none"
                stroke="#2563EB"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />

              {/* Points */}
              {points.map((pt, i) => {
                const isHovered = activePoint === i;
                return (
                  <g
                    key={pt.timeLabel}
                    className="cursor-pointer"
                    onMouseEnter={() => setActivePoint(i)}
                    onMouseLeave={() => setActivePoint(null)}
                  >
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? 6 : 4}
                      fill="#2563EB"
                      stroke="#FFFFFF"
                      strokeWidth="2"
                    />
                    <text
                      x={pt.x}
                      y={height - 12}
                      textAnchor="middle"
                      fontSize="10"
                      fill="#6B7280"
                    >
                      {pt.timeLabel}
                    </text>

                    {/* Tooltip */}
                    {isHovered && (
                      <g transform={`translate(${pt.x}, ${pt.y - 16})`}>
                        <rect
                          x="-28"
                          y="-16"
                          width="56"
                          height="16"
                          rx="2"
                          fill="#1E3A8A"
                        />
                        <text
                          x="0"
                          y="-4"
                          textAnchor="middle"
                          fontSize="9"
                          fill="#FFFFFF"
                          fontWeight="bold"
                        >
                          {pt.frtSec.toFixed(1)} с
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* SLA Compliance Highlights */}
        <div className="lg:col-span-4 space-y-3">
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#1E293B]">
              <ShieldCheck className="size-4 text-[#004B87]" />
              <span>Диспетчеризация очередей (ADR-0005)</span>
            </div>
            <p className="text-[11px] text-[#475569] leading-relaxed">
              Критические сбои P0 при котировочных сессиях моментально поднимаются в начало очереди через <code className="bg-white px-1 py-0.5 border text-[#004B87]">Redis LPUSH</code>.
            </p>
            <div className="text-[11px] text-[#059669] font-semibold flex items-center gap-1 pt-1 border-t border-[#E2E8F0]">
              <CheckCircle2 className="size-3.5 text-[#10B981]" />
              <span>Задержка назначения на слот &lt; 5 сек</span>
            </div>
          </div>

          <div className="bg-[#FAF5FF] border border-[#E9D5FF] p-3 space-y-1.5">
            <div className="flex items-center justify-between text-xs font-bold text-[#6B21A8]">
              <span className="flex items-center gap-1">
                <Activity className="size-3.5" /> AHT Цель: &le; 3.0 мин
              </span>
              <span className="text-[10px] bg-[#E9D5FF] text-[#6B21A8] px-1.5 py-0.2 font-mono">
                Факт: 2.5 мин
              </span>
            </div>
            <p className="text-[11px] text-[#6B21A8]/80 leading-relaxed">
              AI Copilot подсказывает оператору готовые проекты ответов из нормативной базы, сокращая время ручного набора на 42%.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
