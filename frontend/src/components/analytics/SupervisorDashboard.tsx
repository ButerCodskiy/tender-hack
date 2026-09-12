import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  Download,
  RefreshCw,
  Clock,
  CheckCircle2,
  Bot,
  Star,
  Activity,
  Filter,
} from 'lucide-react';
import {
  AnalyticsDashboardMetrics,
  SystemIncident,
  OperatorDailyMetric,
} from '../../types/analytics';
import {
  fetchDashboardMetrics,
  fetchSystemIncidents,
  fetchOperatorMetrics,
  downloadAnalyticsCsv,
} from '../../services/analyticsApi';

interface SupervisorDashboardProps {
  onBackToOperator?: () => void;
}

export const SupervisorDashboard: React.FC<SupervisorDashboardProps> = ({
  onBackToOperator,
}) => {
  const [metrics, setMetrics] = useState<AnalyticsDashboardMetrics | null>(null);
  const [incidents, setIncidents] = useState<SystemIncident[]>([]);
  const [operators, setOperators] = useState<OperatorDailyMetric[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'incidents' | 'operators'>('overview');

  const todayStr = new Date().toISOString().split('T')[0];
  const weekAgoStr = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().split('T')[0];

  const [fromDate, setFromDate] = useState(weekAgoStr);
  const [toDate, setToDate] = useState(todayStr);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [dash, incs, ops] = await Promise.all([
        fetchDashboardMetrics(fromDate, toDate),
        fetchSystemIncidents(),
        fetchOperatorMetrics(),
      ]);
      setMetrics(dash);
      setIncidents(incs);
      setOperators(ops);
    } catch (err) {
      console.error('Ошибка загрузки данных дашборда:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [fromDate, toDate]);

  const handleExportCsv = async () => {
    setIsExporting(true);
    try {
      await downloadAnalyticsCsv(fromDate, toDate);
    } catch (err) {
      console.error('Ошибка выгрузки CSV:', err);
    } finally {
      setIsExporting(false);
    }
  };

  const getIncidentTypeBadge = (type: string) => {
    switch (type) {
      case 'crypto_plugin':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-none text-[11px] font-semibold bg-[#fef2f2] text-[#991b1b] border border-[#fecaca]">
            <ShieldCheck className="size-3 text-[#dc2626]" />
            Сбой плагина ЭЦП
          </span>
        );
      case 'portal_downtime':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-none text-[11px] font-semibold bg-[#fffbeb] text-[#92400e] border border-[#fde68a]">
            <AlertTriangle className="size-3 text-[#d97706]" />
            Недоступность портала
          </span>
        );
      case 'api_error':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-none text-[11px] font-semibold bg-[#f5f3ff] text-[#5b21b6] border border-[#ddd6fe]">
            <Activity className="size-3 text-[#7c3aed]" />
            Ошибка интеграции / API
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-none text-[11px] font-semibold bg-[#f3f4f6] text-[#374151] border border-[#e5e7eb]">
            {type}
          </span>
        );
    }
  };

  return (
    <div className="flex-1 bg-[#F5F6F8] min-h-screen overflow-y-auto custom-scrollbar flex flex-col font-sans">
      {/* Header Bar */}
      <header className="bg-white border-b border-[#E5E7EB] px-6 py-4 shrink-0 flex items-center justify-between sticky top-0 z-20 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="size-9 bg-[#004B87] text-white flex items-center justify-center font-bold text-base shadow-xs">
            Т
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-[#1A1A1A]">
                Аналитический дашборд руководителя
              </h1>
              <span className="px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider bg-[#EAF6FF] text-[#004B87] border border-[#B9DBF7]">
                ЕАИСТ • Контроль качества
              </span>
            </div>
            <p className="text-xs text-[#666666] mt-0.5">
              Мониторинг SLA, арбитраж ответственности операторов и раннее обнаружение сбоев
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Date range filter */}
          <div className="flex items-center gap-1.5 bg-[#F9FAFB] border border-[#D1D5DB] px-2.5 py-1 text-xs text-[#374151]">
            <Filter className="size-3.5 text-[#6B7280]" />
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="bg-transparent border-none text-xs focus:outline-hidden cursor-pointer"
            />
            <span className="text-[#9CA3AF]">—</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="bg-transparent border-none text-xs focus:outline-hidden cursor-pointer"
            />
          </div>

          <button
            type="button"
            onClick={loadData}
            disabled={isLoading}
            className="p-1.5 border border-[#D1D5DB] bg-white hover:bg-[#F3F4F6] text-[#374151] transition cursor-pointer"
            title="Обновить данные"
          >
            <RefreshCw className={`size-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {onBackToOperator && (
            <button
              type="button"
              onClick={onBackToOperator}
              className="flex items-center gap-1 px-3 py-1.5 border border-[#D1D5DB] bg-white hover:bg-[#F3F4F6] text-xs font-semibold text-[#374151] transition cursor-pointer"
              title="Перейти к рабочему месту оператора"
            >
              <span>АРМ Оператора</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleExportCsv}
            disabled={isExporting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#004B87] hover:bg-[#003B6F] text-white text-xs font-bold transition shadow-xs cursor-pointer"
          >
            <Download className="size-3.5" />
            <span>{isExporting ? 'Выгрузка...' : 'Экспорт в Excel (CSV)'}</span>
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="p-6 max-w-7xl w-full mx-auto space-y-6 flex-1">
        {/* KILLER FEATURE CARD: FAIR CSAT / ADJUSTED METRICS */}
        <section className="bg-white border-2 border-[#004B87] p-5 shadow-sm relative overflow-hidden">
          <div className="absolute -right-8 -bottom-8 opacity-5 pointer-events-none">
            <ShieldCheck className="size-64 text-[#004B87]" />
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 bg-[#F0FDF4] border border-[#BBF7D0] text-[#166534] text-xs font-bold">
                <CheckCircle2 className="size-4 text-[#16A34A]" />
                <span>Патентная механика: Справедливый CSAT оператора (Fair Metric)</span>
              </div>
              <h2 className="text-xl font-extrabold text-[#1A1A1A] tracking-tight">
                Автоматическая очистка оценки от инфраструктурных сбоев
              </h2>
              <p className="text-xs text-[#4B5563] leading-relaxed">
                Если поставщик поставил 1 звезду из-за отказа плагина КриптоПро, СМЭВ или зависания Портала,
                нейросеть-аудитор (LLM-Judge) классифицирует первопричину как <code className="bg-[#F3F4F6] px-1 py-0.5 text-[#111827] font-bold">root_cause = system_issue</code>.
                Оценка исключается из личного рейтинга оператора и регистрируется в реестре аварий.
              </p>
            </div>

            {/* Score Comparison Display */}
            <div className="flex items-center gap-4 bg-[#F8FAFC] border border-[#E2E8F0] p-4 shrink-0 shadow-inner">
              <div className="text-center px-3 border-r border-[#CBD5E1]">
                <span className="text-[11px] font-semibold text-[#64748B] block uppercase tracking-wider">
                  Сырой CSAT
                </span>
                <div className="text-2xl font-bold text-[#94A3B8] line-through mt-0.5">
                  {metrics?.client_csat.toFixed(2) || '3.42'} ★
                </div>
                <span className="text-[10px] text-[#EF4444] font-semibold block mt-0.5">
                  С учетом сбоев ЭЦП
                </span>
              </div>

              <div className="text-center px-3">
                <span className="text-[11px] font-bold text-[#004B87] block uppercase tracking-wider">
                  Adjusted CSAT
                </span>
                <div className="text-3xl font-extrabold text-[#16A34A] flex items-center justify-center gap-1 mt-0.5">
                  <span>{metrics?.adjusted_csat.toFixed(2) || '4.86'}</span>
                  <Star className="size-6 fill-[#16A34A] text-[#16A34A]" />
                </div>
                <span className="text-[10px] bg-[#DCFCE7] text-[#15803D] font-bold px-1.5 py-0.5 mt-0.5 inline-block">
                  +{( (metrics?.adjusted_csat || 4.86) - (metrics?.client_csat || 3.42) ).toFixed(2)} к справедливости
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* METRICS KPI GRID */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Deflection Rate */}
          <div className="bg-white border border-[#E5E7EB] p-4 space-y-2 shadow-2xs hover:border-[#004B87] transition">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#6B7280]">Доля решения ботом (Deflection)</span>
              <div className="size-8 bg-[#EAF6FF] text-[#004B87] flex items-center justify-center">
                <Bot className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-extrabold text-[#111827]">
              {metrics?.bot_resolved_percent.toFixed(1) || '42.6'}%
            </div>
            <p className="text-[11px] text-[#059669] font-medium flex items-center gap-1">
              <TrendingUp className="size-3" />
              <span>{metrics?.bot_resolved_tickets || 63} обращений закрыто без человека</span>
            </p>
          </div>

          {/* Card 2: First Response Time */}
          <div className="bg-white border border-[#E5E7EB] p-4 space-y-2 shadow-2xs hover:border-[#004B87] transition">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#6B7280]">Время 1-го ответа (FRT)</span>
              <div className="size-8 bg-[#FEF3C7] text-[#D97706] flex items-center justify-center">
                <Clock className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-extrabold text-[#111827]">
              {Math.round(metrics?.avg_first_response_time_sec || 46)} сек
            </div>
            <p className="text-[11px] text-[#059669] font-medium">
              Норматив SLA (P0 &lt; 60 с): <span className="font-bold">Выполняется 98.4%</span>
            </p>
          </div>

          {/* Card 3: Average Handling Time */}
          <div className="bg-white border border-[#E5E7EB] p-4 space-y-2 shadow-2xs hover:border-[#004B87] transition">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#6B7280]">Время решения (AHT)</span>
              <div className="size-8 bg-[#F3E8FF] text-[#7C3AED] flex items-center justify-center">
                <Activity className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-extrabold text-[#111827]">
              {Math.round((metrics?.avg_handling_time_sec || 215) / 60)} мин {(Math.round(metrics?.avg_handling_time_sec || 215) % 60)} сек
            </div>
            <p className="text-[11px] text-[#6B7280]">
              Всего тикетов в периоде: <span className="font-bold text-[#111827]">{metrics?.total_tickets || 148}</span>
            </p>
          </div>

          {/* Card 4: Active Incidents */}
          <div className="bg-white border border-[#E5E7EB] p-4 space-y-2 shadow-2xs hover:border-[#DC2626] transition">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#6B7280]">Активные системные сбои</span>
              <div className="size-8 bg-[#FEE2E2] text-[#DC2626] flex items-center justify-center">
                <AlertTriangle className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-extrabold text-[#DC2626] flex items-center gap-2">
              <span>{metrics?.active_incidents_count || incidents.filter((i) => i.status === 'open').length}</span>
              <span className="size-2 rounded-full bg-[#DC2626] animate-pulse" />
            </div>
            <p className="text-[11px] text-[#B91C1C] font-medium">
              Раннее предупреждение до вала жалоб
            </p>
          </div>
        </section>

        {/* TABS NAVIGATION */}
        <div className="border-b border-[#D1D5DB] flex items-center gap-6 text-xs font-bold">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`pb-2.5 transition border-b-2 cursor-pointer ${
              activeTab === 'overview'
                ? 'border-[#004B87] text-[#004B87]'
                : 'border-transparent text-[#6B7280] hover:text-[#111827]'
            }`}
          >
            Сводка и Рейтинг операторов ({operators.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('incidents')}
            className={`pb-2.5 transition border-b-2 cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'incidents'
                ? 'border-[#004B87] text-[#004B87]'
                : 'border-transparent text-[#6B7280] hover:text-[#111827]'
            }`}
          >
            <span>Реестр системных инцидентов</span>
            <span className="px-1.5 py-0.2 rounded-full bg-[#DC2626] text-white text-[10px] font-bold">
              {incidents.filter((i) => i.status === 'open').length}
            </span>
          </button>
        </div>

        {/* TAB 1: OPERATOR RANKING TABLE */}
        {activeTab === 'overview' && (
          <section className="bg-white border border-[#E5E7EB] shadow-xs">
            <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between bg-[#F9FAFB]">
              <div>
                <h3 className="text-xs font-bold text-[#111827] uppercase tracking-wider">
                  Суточный срез эффективности операторов
                </h3>
                <p className="text-[11px] text-[#6B7280]">
                  Сравнение сырого клиентского рейтинга и скорректированного CSAT по методике ЕАИСТ
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#F3F4F6] text-[#4B5563] font-bold uppercase tracking-wider text-[10px] border-b border-[#E5E7EB]">
                  <tr>
                    <th className="py-2.5 px-4">Сотрудник</th>
                    <th className="py-2.5 px-4">Линия</th>
                    <th className="py-2.5 px-4 text-center">Тикетов</th>
                    <th className="py-2.5 px-4 text-center">FRT</th>
                    <th className="py-2.5 px-4 text-center">AHT</th>
                    <th className="py-2.5 px-4 text-center">Сырой CSAT</th>
                    <th className="py-2.5 px-4 text-center font-extrabold text-[#004B87]">
                      Adjusted CSAT
                    </th>
                    <th className="py-2.5 px-4 text-center">ИИ-аудит (AI-QA)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E7EB] text-[#1F2937]">
                  {operators.map((op) => (
                    <tr key={op.operator_id} className="hover:bg-[#F9FAFB] transition">
                      <td className="py-3 px-4 font-semibold text-[#111827]">
                        <div className="flex items-center gap-2">
                          <div className="size-6 rounded-full bg-[#EAF6FF] text-[#004B87] font-bold text-[10px] flex items-center justify-center">
                            {op.operator_name.split(' ').map((n) => n[0]).slice(0, 2).join('')}
                          </div>
                          <span>{op.operator_name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="font-mono px-2 py-0.5 bg-[#F3F4F6] text-[#374151] border border-[#E5E7EB] text-[10px] font-bold">
                          {op.line_code}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center font-medium">
                        {op.total_tickets_handled}
                      </td>
                      <td className="py-3 px-4 text-center font-mono text-[11px]">
                        {Math.round(op.avg_first_response_time_sec || 0)} с
                      </td>
                      <td className="py-3 px-4 text-center font-mono text-[11px]">
                        {Math.round((op.avg_handling_time_sec || 0) / 60)}м {(Math.round(op.avg_handling_time_sec || 0) % 60)}с
                      </td>
                      <td className="py-3 px-4 text-center text-[#9CA3AF] line-through font-mono">
                        {op.avg_client_csat ? op.avg_client_csat.toFixed(2) : '—'}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="inline-flex items-center gap-1 font-bold text-[#16A34A] bg-[#DCFCE7] px-2 py-0.5 border border-[#BBF7D0]">
                          <span>{op.avg_adjusted_csat ? op.avg_adjusted_csat.toFixed(2) : '5.00'}</span>
                          <Star className="size-3 fill-[#16A34A] text-[#16A34A]" />
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-[#004B87]">
                        {op.avg_ai_quality_score ? op.avg_ai_quality_score.toFixed(2) : '4.80'} / 5.0
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* TAB 2: INCIDENTS REGISTRY */}
        {activeTab === 'incidents' && (
          <section className="bg-white border border-[#E5E7EB] shadow-xs">
            <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between bg-[#F9FAFB]">
              <div>
                <h3 className="text-xs font-bold text-[#111827] uppercase tracking-wider">
                  Реестр технических инцидентов и отказов платформы
                </h3>
                <p className="text-[11px] text-[#6B7280]">
                  Сформирован автоматически модулем LLM-Judge при аудите обращений клиентов
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#F3F4F6] text-[#4B5563] font-bold uppercase tracking-wider text-[10px] border-b border-[#E5E7EB]">
                  <tr>
                    <th className="py-2.5 px-4">Тип сбоя</th>
                    <th className="py-2.5 px-4">Тикет</th>
                    <th className="py-2.5 px-4">Описание симптомов сбоя</th>
                    <th className="py-2.5 px-4 text-center">Статус</th>
                    <th className="py-2.5 px-4 text-right">Время фиксации</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E7EB] text-[#1F2937]">
                  {incidents.map((inc) => (
                    <tr key={inc.id} className="hover:bg-[#F9FAFB] transition">
                      <td className="py-3 px-4 whitespace-nowrap">
                        {getIncidentTypeBadge(inc.incident_type)}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-[#4B5563]">
                        #{inc.ticket_id}
                      </td>
                      <td className="py-3 px-4 text-[#111827] max-w-md font-medium leading-relaxed">
                        {inc.description}
                      </td>
                      <td className="py-3 px-4 text-center whitespace-nowrap">
                        {inc.status === 'open' ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase bg-[#FEE2E2] text-[#B91C1C] border border-[#FCA5A5]">
                            <span className="size-1.5 rounded-full bg-[#DC2626] animate-ping" />
                            ОТКРЫТ
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase bg-[#DCFCE7] text-[#15803D] border border-[#BBF7D0]">
                            РЕШЕН
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right text-[#6B7280] font-mono text-[11px] whitespace-nowrap">
                        {new Date(inc.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })},{' '}
                        {new Date(inc.created_at).toLocaleDateString([], { day: '2-digit', month: '2-digit' })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
};
