import React, { useState } from 'react';
import {
  Headphones,
  CircleDot,
  CheckCircle2,
  Clock,
  LogOut,
  ChevronDown,
  User,
  Coffee,
  PowerOff,
  Radio,
  ArrowLeftRight,
} from 'lucide-react';
import {
  OperatorProfile,
  OperatorSidebarTicket,
  ShiftStatus,
  TicketPriority,
} from '../../types/operator';
import { UserProfile } from '../../types/auth';

interface OperatorSidebarProps {
  profile: OperatorProfile;
  tickets: OperatorSidebarTicket[];
  activeTicketId: string | null;
  onSelectTicket: (ticketId: string) => void;
  onUpdateShift: (status: ShiftStatus) => void;
  user: UserProfile | null;
  onLogout: () => void;
  onSwitchToClientMode: () => void;
}

export const OperatorSidebar: React.FC<OperatorSidebarProps> = ({
  profile,
  tickets,
  activeTicketId,
  onSelectTicket,
  onUpdateShift,
  user,
  onLogout,
  onSwitchToClientMode,
}) => {
  const [isShiftDropdownOpen, setIsShiftDropdownOpen] = useState(false);
  const [filterPriority, setFilterPriority] = useState<'all' | TicketPriority>('all');

  const filteredTickets = tickets.filter((t) => {
    if (filterPriority === 'all') return true;
    return t.priority === filterPriority;
  });

  const getShiftBadge = (status: ShiftStatus) => {
    switch (status) {
      case 'active':
        return {
          label: 'На линии',
          dot: 'bg-emerald-500',
          color: 'bg-emerald-50 text-emerald-700 border-emerald-200',
          icon: Radio,
        };
      case 'break':
        return {
          label: 'Перерыв',
          dot: 'bg-amber-500',
          color: 'bg-amber-50 text-amber-700 border-amber-200',
          icon: Coffee,
        };
      case 'offline':
        return {
          label: 'Не в сети',
          dot: 'bg-gray-400',
          color: 'bg-gray-100 text-gray-700 border-gray-200',
          icon: PowerOff,
        };
    }
  };

  const currentShift = getShiftBadge(profile.shift_status);

  const getPriorityBadge = (p: TicketPriority) => {
    switch (p) {
      case 'P0':
        return {
          label: 'P0 Критический',
          badge: 'bg-red-50 text-red-600 border-red-200 font-bold',
        };
      case 'P1':
        return {
          label: 'P1 Срочный',
          badge: 'bg-amber-50 text-amber-700 border-amber-200 font-semibold',
        };
      case 'P2':
        return {
          label: 'P2 Стандарт',
          badge: 'bg-primary-50 text-primary-600 border-primary-200 font-medium',
        };
    }
  };

  return (
    <aside className="w-80 flex flex-col bg-white border-r border-gray-100 h-dvh select-none shrink-0 z-20">
      {/* Header with Branding & Line */}
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="size-9 rounded-xl bg-gradient-to-tr from-primary-600 to-primary-400 flex items-center justify-center text-white shadow-2xs">
            <Headphones className="size-4.5" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-title-50 leading-tight flex items-center gap-1.5">
              <span>АРМ Оператора</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-primary-100 text-primary-700 font-bold border border-primary-200">
                {profile.line_code}
              </span>
            </h1>
            <span className="text-[11px] text-text-100">Служба поддержки Портала</span>
          </div>
        </div>

        <button
          type="button"
          onClick={onSwitchToClientMode}
          title="Переключиться в режим клиента (поставщика)"
          className="p-1.5 rounded-xl border border-gray-200 text-gray-500 hover:text-primary-600 hover:bg-primary-50 transition cursor-pointer"
        >
          <ArrowLeftRight className="size-4" />
        </button>
      </div>

      {/* Shift Controller Card */}
      <div className="p-3 border-b border-gray-100 bg-gray-50/50">
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsShiftDropdownOpen(!isShiftDropdownOpen)}
            className={`w-full flex items-center justify-between p-2.5 rounded-2xl border text-xs font-semibold shadow-2xs transition cursor-pointer ${currentShift.color}`}
          >
            <div className="flex items-center gap-2">
              <span className={`size-2.5 rounded-full ${currentShift.dot} animate-pulse`} />
              <span>Статус: {currentShift.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono opacity-80">
                {profile.active_slots_count}/{profile.max_slots} слотов
              </span>
              <ChevronDown className="size-3.5" />
            </div>
          </button>

          {/* Shift Dropdown */}
          {isShiftDropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-1.5 bg-white rounded-2xl border border-gray-100 shadow-xl p-1.5 z-30 space-y-0.5 animate-in fade-in duration-150">
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('active');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-medium text-gray-700 hover:bg-emerald-50 hover:text-emerald-800 transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-emerald-500" />
                <span>На линии (принимать тикеты)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('break');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-medium text-gray-700 hover:bg-amber-50 hover:text-amber-800 transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-amber-500" />
                <span>Перерыв (пауза распределения)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('offline');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-gray-400" />
                <span>Не в сети (завершить смену)</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="px-3 pt-3 pb-2 flex items-center gap-1 border-b border-gray-100/80">
        <button
          type="button"
          onClick={() => setFilterPriority('all')}
          className={`flex-1 py-1 text-[11px] font-semibold rounded-lg transition cursor-pointer text-center ${
            filterPriority === 'all'
              ? 'bg-primary-50 text-primary-600 border border-primary-100'
              : 'text-gray-500 hover:bg-gray-100'
          }`}
        >
          Все ({tickets.length})
        </button>
        <button
          type="button"
          onClick={() => setFilterPriority('P0')}
          className={`flex-1 py-1 text-[11px] font-semibold rounded-lg transition cursor-pointer text-center ${
            filterPriority === 'P0'
              ? 'bg-red-50 text-red-600 border border-red-200'
              : 'text-gray-500 hover:bg-gray-100'
          }`}
        >
          P0 Срочные
        </button>
        <button
          type="button"
          onClick={() => setFilterPriority('P1')}
          className={`flex-1 py-1 text-[11px] font-semibold rounded-lg transition cursor-pointer text-center ${
            filterPriority === 'P1'
              ? 'bg-amber-50 text-amber-700 border border-amber-200'
              : 'text-gray-500 hover:bg-gray-100'
          }`}
        >
          P1
        </button>
      </div>

      {/* Ticket List */}
      <div className="flex-1 overflow-y-auto p-2.5 custom-scrollbar space-y-1.5">
        {filteredTickets.length === 0 ? (
          <div className="py-12 text-center text-xs text-gray-400 space-y-2">
            <CheckCircle2 className="size-8 mx-auto text-gray-300 stroke-[1.5]" />
            <p>Очередь свободна</p>
            <p className="text-[11px] text-gray-400">Нет назначенных тикетов в выбранной категории</p>
          </div>
        ) : (
          filteredTickets.map((t) => {
            const isSelected = activeTicketId === t.ticket_id;
            const prio = getPriorityBadge(t.priority);

            return (
              <div
                key={t.ticket_id}
                onClick={() => onSelectTicket(t.ticket_id)}
                className={`p-3 rounded-2xl border transition-all cursor-pointer select-none ${
                  isSelected
                    ? 'bg-primary-50/50 border-primary-300 shadow-xs ring-1 ring-primary-300'
                    : 'bg-white border-gray-100 hover:border-gray-200 hover:bg-gray-50/60'
                }`}
              >
                <div className="flex items-center justify-between gap-1.5 mb-1.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md border ${prio.badge}`}>
                    {prio.label}
                  </span>
                  <div className="flex items-center gap-1 text-[11px] text-gray-400">
                    <Clock className="size-3" />
                    <span>{t.created_at}</span>
                  </div>
                </div>

                <div className="truncate">
                  <span className="text-xs font-bold text-title-50 block truncate">
                    {t.company_name || t.client_name || 'Поставщик'}
                  </span>
                  {t.client_name && t.company_name && (
                    <span className="text-[11px] text-gray-500 block truncate">
                      {t.client_name}
                    </span>
                  )}
                </div>

                {t.last_message_preview && (
                  <p className="text-[11px] text-gray-600 line-clamp-2 mt-1 leading-relaxed">
                    {t.last_message_preview}
                  </p>
                )}

                <div className="flex items-center justify-between pt-2 mt-2 border-t border-gray-100/70 text-[10px]">
                  <span className="flex items-center gap-1 text-gray-500">
                    <CircleDot className="size-2.5 text-primary-500" />
                    <span>{t.status === 'in_progress' ? 'В работе' : 'Назначен'}</span>
                  </span>
                  {t.unread_messages_count > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-red-500 text-white font-bold text-[10px]">
                      +{t.unread_messages_count}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Operator User Card Footer */}
      <div className="p-3 border-t border-gray-100">
        <div className="flex items-center justify-between p-2 rounded-2xl bg-gray-50 border border-gray-100">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="size-8 rounded-full bg-white border border-gray-200 flex items-center justify-center text-primary-600 shrink-0 font-semibold shadow-2xs">
              <User className="size-4" />
            </div>
            <div className="truncate">
              <span className="text-xs font-semibold text-title-50 block truncate">
                {user?.full_name || profile.full_name}
              </span>
              <span className="text-[10px] text-gray-500 block truncate">
                Оператор 1-й линии
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            title="Выйти из аккаунта"
            className="size-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
          >
            <LogOut className="size-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
};
