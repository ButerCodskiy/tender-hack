import {
  AnalyticsDashboardMetrics,
  SystemIncident,
  OperatorDailyMetric,
} from '../types/analytics';
import { getStoredTokens } from './auth';
import { isStandaloneMode } from '../config/mode';

const MOCK_DASHBOARD: AnalyticsDashboardMetrics = {
  from_date: new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
  to_date: new Date().toISOString().split('T')[0],
  total_tickets: 148,
  bot_resolved_tickets: 63,
  bot_resolved_percent: 42.6,
  avg_first_response_time_sec: 46.2,
  avg_handling_time_sec: 214.8,
  client_csat: 3.42,
  adjusted_csat: 4.86,
  avg_ai_politeness_score: 4.88,
  avg_ai_completeness_score: 4.72,
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
  },
  {
    id: 'inc-002',
    ticket_id: 't-084',
    incident_type: 'portal_downtime',
    description: 'Таймаут шлюза СМЭВ при автоматической валидации МЧД из реестра ФНС',
    status: 'open',
    created_at: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    resolved_at: null,
  },
  {
    id: 'inc-003',
    ticket_id: 't-072',
    incident_type: 'crypto_plugin',
    description: 'Несовместимость сборки cadesplugin 2.0 с обновлением Chromium 128',
    status: 'open',
    created_at: new Date(Date.now() - 180 * 60 * 1000).toISOString(),
    resolved_at: null,
  },
  {
    id: 'inc-004',
    ticket_id: 't-055',
    incident_type: 'api_error',
    description: 'Сбой синхронизации статусов оферт ЕАИСТ с ЕИС Закупки (504 Gateway Timeout)',
    status: 'resolved',
    created_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    resolved_at: new Date(Date.now() - 20 * 3600 * 1000).toISOString(),
  },
];

const MOCK_OPERATORS: OperatorDailyMetric[] = [
  {
    operator_id: 'op-001',
    operator_name: 'Смирнова Анна Сергеевна',
    line_code: 'L1',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 28,
    avg_first_response_time_sec: 38.4,
    avg_handling_time_sec: 185.0,
    avg_client_csat: 3.55,
    avg_adjusted_csat: 4.92,
    avg_ai_quality_score: 4.85,
  },
  {
    operator_id: 'op-002',
    operator_name: 'Кузнецов Михаил Романович',
    line_code: 'L2',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 19,
    avg_first_response_time_sec: 52.1,
    avg_handling_time_sec: 310.4,
    avg_client_csat: 3.20,
    avg_adjusted_csat: 4.80,
    avg_ai_quality_score: 4.75,
  },
  {
    operator_id: 'op-003',
    operator_name: 'Васильева Елена Игоревна',
    line_code: 'L1',
    metric_date: new Date().toISOString().split('T')[0],
    total_tickets_handled: 24,
    avg_first_response_time_sec: 42.0,
    avg_handling_time_sec: 195.2,
    avg_client_csat: 3.65,
    avg_adjusted_csat: 4.88,
    avg_ai_quality_score: 4.80,
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

  // Fallback CSV генерация
  const csvRows = [
    '\uFEFFticket_id,created_at,status,line_code,feedback_score,is_system_issue,adjusted_csat,summary',
    't-101,2026-09-12 14:20:00,resolved,L2,1,true,4.86,"Сбой плагина ЭЦП 0x80090014 при подписании КС-9482"',
    't-102,2026-09-12 14:05:00,resolved,L1,5,false,5.00,"Консультация по регламенту котировочных сессий"',
    't-103,2026-09-12 13:40:00,resolved,L1,4,false,4.00,"Сроки подачи протокола разногласий по 44-ФЗ"',
    't-084,2026-09-12 12:15:00,resolved,L2,1,true,4.86,"Таймаут синхронизации МЧД в ФНС"',
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
