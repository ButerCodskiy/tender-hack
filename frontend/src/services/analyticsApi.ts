import {
  AnalyticsDashboardMetrics,
  SystemIncident,
  OperatorDailyMetric,
  DeflectionTrendPoint,
  CategoryBreakdown,
  SlaTimelinePoint,
  CsatDistributionPoint,
} from '../types/analytics';
import { getStoredTokens } from './auth';
import { isStandaloneMode } from '../config/mode';

const MOCK_DASHBOARD: AnalyticsDashboardMetrics = {
  from_date: new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
  to_date: new Date().toISOString().split('T')[0],
  total_tickets: 156,
  bot_resolved_tickets: 106,
  bot_resolved_percent: 68.0,
  avg_first_response_time_sec: 18.0,
  avg_handling_time_sec: 150.0,
  client_csat: 3.42,
  adjusted_csat: 4.78,
  avg_ai_politeness_score: 4.90,
  avg_ai_completeness_score: 4.82,
  active_incidents_count: 3,
};

const MOCK_INCIDENTS: SystemIncident[] = [
  {
    id: 'inc-001',
    ticket_id: 't-101',
    incident_type: 'crypto_plugin',
    description: 'Массовая ошибка плагина ЭЦП КриптоПро (0x80090014) при подписании контракта КС-9482',
    status: 'open',
    created_at: new Date(Date.now() - 25 * 60 * 1000).toISOString(),
    resolved_at: null,
    error_code: '0x80090014',
    llm_verdict: 'Классифицировано LLM-Judge как root_cause=system_issue (несовместимость cadesplugin с Chromium). Оценка поставщика (1 звезда) исключена из рейтинга оператора Кузнецова М.Р. Тикет перенаправлен в баг-трекер платформы.',
    raw_score: 1,
    adjusted_score: 5,
    dialog_excerpt: 'Поставщик: "Не могу подписать проект контракта КС-9482! Выскакивает окно 0x80090014 Плагин недоступен! До дедлайна 30 минут, вы сорвали сделку!"\nОператор L2: "Здравствуйте! Зафиксировали массовый сбой КриптоПро ЭЦП, передали в отдел инфраструктуры. Для срочного подписания используйте резервный ГОСТ-браузер Яндекс."',
    operator_name: 'Кузнецов Михаил Романович (L2)',
  },
  {
    id: 'inc-002',
    ticket_id: 't-084',
    incident_type: 'portal_downtime',
    description: 'Таймаут шлюза СМЭВ при автоматической валидации МЧД из реестра ФНС',
    status: 'open',
    created_at: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    resolved_at: null,
    error_code: 'SMEV_504_TIMEOUT',
    llm_verdict: 'Классифицировано LLM-Judge как root_cause=external_dependency (внешний таймаут сервиса ФНС России). Оператор действовал строго по регламенту Р-04. Оценка 1 звезда исключена.',
    raw_score: 1,
    adjusted_score: 5,
    dialog_excerpt: 'Поставщик: "МЧД висит на проверке уже два часа! Кнопка подачи предложения заблокирована!"\nОператор L1: "По регламенту ЕАИСТ проверка доверенности занимает до 15 минут, сейчас шлюз ФНС перегружен. Заявка поставлена в приоритетную очередь."',
    operator_name: 'Смирнова Анна Сергеевна (L1)',
  },
  {
    id: 'inc-003',
    ticket_id: 't-072',
    incident_type: 'crypto_plugin',
    description: 'Несовместимость сборки cadesplugin 2.0 с обновлением Chromium 128',
    status: 'open',
    created_at: new Date(Date.now() - 180 * 60 * 1000).toISOString(),
    resolved_at: null,
    error_code: '0x80090016',
    llm_verdict: 'Классифицировано LLM-Judge как root_cause=system_issue (сбой библиотеки cadesplugin при вызове CPSignHash). Оценка 1 звезда исключена из расчета KPI.',
    raw_score: 1,
    adjusted_score: 5,
    dialog_excerpt: 'Поставщик: "После автообновления браузера слетела ЭЦП! Ошибка 0x80090016. Оператор ничем не помог!"\nОператор L2: "Рекомендуем переустановить расширение КриптоПро версии 2.0.14892 и очистить кэш сертификатов."',
    operator_name: 'Кузнецов Михаил Романович (L2)',
  },
  {
    id: 'inc-004',
    ticket_id: 't-055',
    incident_type: 'api_error',
    description: 'Сбой синхронизации статусов оферт ЕАИСТ с ЕИС Закупки (504 Gateway Timeout)',
    status: 'resolved',
    created_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    resolved_at: new Date(Date.now() - 20 * 3600 * 1000).toISOString(),
    error_code: 'EIS_SYNC_504',
    llm_verdict: 'Классифицировано LLM-Judge как root_cause=system_issue. Инцидент закрыт после восстановления работы очередей RabbitMQ/Celery.',
    raw_score: 2,
    adjusted_score: 5,
    dialog_excerpt: 'Поставщик: "Оферта не выгружается в ЕИС уже сутки!"\nОператор L1: "Синхронизация возобновлена, статус обновился автоматически."',
    operator_name: 'Васильева Елена Игоревна (L1)',
  },
];

const MOCK_OPERATORS: OperatorDailyMetric[] = [
  {
    operator_id: 'op-001',
    operator_name: 'Смирнова Анна Сергеевна',
    line_code: 'L1',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 32,
    avg_first_response_time_sec: 16.5,
    avg_handling_time_sec: 140.0,
    avg_client_csat: 3.55,
    avg_adjusted_csat: 4.88,
    avg_ai_quality_score: 4.90,
  },
  {
    operator_id: 'op-002',
    operator_name: 'Кузнецов Михаил Романович',
    line_code: 'L2',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 24,
    avg_first_response_time_sec: 21.0,
    avg_handling_time_sec: 210.0,
    avg_client_csat: 3.20,
    avg_adjusted_csat: 4.75,
    avg_ai_quality_score: 4.82,
  },
  {
    operator_id: 'op-003',
    operator_name: 'Васильева Елена Игоревна',
    line_code: 'L1',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 28,
    avg_first_response_time_sec: 17.8,
    avg_handling_time_sec: 155.0,
    avg_client_csat: 3.65,
    avg_adjusted_csat: 4.85,
    avg_ai_quality_score: 4.88,
  },
];

export async function fetchDashboardMetrics(
  fromDate?: string,
  toDate?: string
): Promise<AnalyticsDashboardMetrics> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const params = new URLSearchParams();
      if (fromDate) params.append('from_date', fromDate);
      if (toDate) params.append('to_date', toDate);

      const res = await fetch(`/api/v1/analytics/dashboard?${params.toString()}`, {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });

      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('Ошибка загрузки дашборда с сервера, включен мок:', err);
    }
  }

  return MOCK_DASHBOARD;
}

export async function fetchSystemIncidents(
  status?: string,
  incidentType?: string
): Promise<SystemIncident[]> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const params = new URLSearchParams();
      if (status) params.append('status', status);
      if (incidentType) params.append('incident_type', incidentType);

      const res = await fetch(`/api/v1/analytics/incidents?${params.toString()}`, {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });

      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('Ошибка загрузки инцидентов с сервера, включен мок:', err);
    }
  }

  let filtered = MOCK_INCIDENTS;
  if (status) {
    filtered = filtered.filter((i) => i.status === status);
  }
  if (incidentType) {
    filtered = filtered.filter((i) => i.incident_type === incidentType);
  }
  return filtered;
}

export async function fetchOperatorMetrics(
  date?: string,
  lineCode?: string
): Promise<OperatorDailyMetric[]> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const params = new URLSearchParams();
      if (date) params.append('date', date);
      if (lineCode) params.append('line_code', lineCode);

      const res = await fetch(`/api/v1/analytics/operators?${params.toString()}`, {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });

      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('Ошибка загрузки операторов с сервера, включен мок:', err);
    }
  }

  let filtered = MOCK_OPERATORS;
  if (lineCode) {
    filtered = filtered.filter((o) => o.line_code === lineCode);
  }
  return filtered;
}

export async function downloadAnalyticsCsv(
  fromDate: string,
  toDate: string
): Promise<void> {
  const filename = `analytics_export_${fromDate}_${toDate}.csv`;

  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const params = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        format: 'csv',
      });

      const res = await fetch(`/api/v1/analytics/export?${params.toString()}`, {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        return;
      }
    } catch (err) {
      console.warn('Ошибка выгрузки CSV с сервера, генерация локального CSV:', err);
    }
  }

  // Fallback CSV генерация с UTF-8 BOM (\uFEFF) для полной совместимости с Excel
  const csvRows = [
    '\uFEFFticket_id,created_at,status,line_code,operator,feedback_score,is_system_issue,root_cause,adjusted_csat,summary',
    't-101,2026-09-12 14:20:00,resolved,L2,"Кузнецов М.Р.",1,true,crypto_plugin,4.78,"Сбой плагина ЭЦП 0x80090014 при подписании КС-9482"',
    't-102,2026-09-12 14:05:00,resolved,L1,"Смирнова А.С.",5,false,none,5.00,"Консультация по регламенту котировочных сессий"',
    't-103,2026-09-12 13:40:00,resolved,L1,"Васильева Е.И.",4,false,none,4.00,"Сроки подачи протокола разногласий по 44-ФЗ"',
    't-084,2026-09-12 12:15:00,resolved,L1,"Смирнова А.С.",1,true,portal_downtime,4.78,"Таймаут синхронизации МЧД в ФНС"',
    't-072,2026-09-12 11:30:00,resolved,L2,"Кузнецов М.Р.",1,true,crypto_plugin,4.78,"Несовместимость сборки cadesplugin 2.0 с Chromium 128"',
    't-055,2026-09-12 10:10:00,resolved,L1,"Васильева Е.И.",5,false,none,5.00,"Синхронизация оферт ЕАИСТ с ЕИС Закупки"',
  ];

  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function getMockDeflectionTrend(): DeflectionTrendPoint[] {
  return [
    { dayLabel: 'Пн', rate: 48.2, botCount: 68, totalCount: 141 },
    { dayLabel: 'Вт', rate: 52.4, botCount: 76, totalCount: 145 },
    { dayLabel: 'Ср', rate: 57.0, botCount: 85, totalCount: 149 },
    { dayLabel: 'Чт', rate: 61.5, botCount: 94, totalCount: 153 },
    { dayLabel: 'Пт', rate: 64.8, botCount: 99, totalCount: 153 },
    { dayLabel: 'Сб', rate: 66.2, botCount: 78, totalCount: 118 },
    { dayLabel: 'Вс', rate: 68.0, botCount: 106, totalCount: 156 },
  ];
}

export function getMockCategoryBreakdown(): CategoryBreakdown[] {
  return [
    { label: 'Регламенты 44-ФЗ и сроки', count: 48, share: 30.8, color: '#004B87' },
    { label: 'Оферты и спецификации', count: 35, share: 22.4, color: '#2563EB' },
    { label: 'Каталог СТЕ и YML-прайсы', count: 23, share: 14.8, color: '#0EA5E9' },
    { label: 'МЧД и полномочия', count: 18, share: 11.5, color: '#10B981' },
    { label: 'ЭЦП и плагины (L2)', count: 32, share: 20.5, color: '#E31E24' },
  ];
}

export function getMockSlaTimeline(): SlaTimelinePoint[] {
  return [
    { timeLabel: '09:00', frtSec: 14.2, slaTargetSec: 60, ahtSec: 135 },
    { timeLabel: '11:00', frtSec: 16.8, slaTargetSec: 60, ahtSec: 148 },
    { timeLabel: '13:00', frtSec: 22.4, slaTargetSec: 60, ahtSec: 162 },
    { timeLabel: '15:00', frtSec: 19.1, slaTargetSec: 60, ahtSec: 155 },
    { timeLabel: '17:00', frtSec: 17.5, slaTargetSec: 60, ahtSec: 144 },
    { timeLabel: '19:00', frtSec: 15.0, slaTargetSec: 60, ahtSec: 138 },
  ];
}

export function getMockCsatDistribution(): CsatDistributionPoint[] {
  return [
    { stars: 5, rawCount: 88, adjustedCount: 88, excludedCount: 0 },
    { stars: 4, rawCount: 28, adjustedCount: 28, excludedCount: 0 },
    { stars: 3, rawCount: 12, adjustedCount: 12, excludedCount: 0 },
    { stars: 2, rawCount: 6, adjustedCount: 4, excludedCount: 2 },
    { stars: 1, rawCount: 22, adjustedCount: 2, excludedCount: 20 },
  ];
}

