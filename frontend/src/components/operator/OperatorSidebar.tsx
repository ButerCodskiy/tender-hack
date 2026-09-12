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
          badge: 'bg-[#fef0ef] text-[#db2b21] border-[#db2b21]/40 font-bold',
        };
      case 'P1':
        return {
          label: 'P1 Срочный',
          badge: 'bg-[#fff3ec] text-[#f67319] border-[#f67319]/40 font-bold',
        };
      case 'P2':
        return {
          label: 'P2 Стандарт',
          badge: 'bg-[#eaf6ff] text-[#264b82] border-[#264b82]/30 font-bold',
        };
    }
  };

  return (
    <aside className="w-80 flex flex-col bg-white border-r border-[#e5e5e5] h-full select-none shrink-0 z-20">
      {/* Header with Branding & Line */}
      <div className="p-3.5 border-b border-[#e5e5e5] flex items-center justify-between h-14">
        <div className="flex items-center gap-2.5">
          <div className="size-8 rounded-none bg-[#264b82] flex items-center justify-center text-white shrink-0 font-bold">
            <Headphones className="size-4.5" />
          </div>
          <div>
            <h1 className="text-xs font-bold text-[#1a1a1a] leading-tight flex items-center gap-1.5">
              <span>АРМ Оператора</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-none bg-[#264b82] text-white font-bold">
                {profile.line_code}
              </span>
            </h1>
            <span className="text-[11px] text-[#7f8792]">Служба поддержки ЕАИСТ</span>
          </div>
        </div>

        <button
          type="button"
          onClick={onSwitchToClientMode}
          title="Переключиться в режим клиента (поставщика)"
          className="p-1.5 rounded-none border border-[#22242626] text-[#7f8792] hover:text-[#264b82] hover:bg-[#f2f7fc] transition cursor-pointer"
        >
          <ArrowLeftRight className="size-4" />
        </button>
      </div>

      {/* Shift Controller Card */}
      <div className="p-2.5 border-b border-[#e5e5e5] bg-[#f7f8f9]">
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsShiftDropdownOpen(!isShiftDropdownOpen)}
            className={`w-full flex items-center justify-between p-2 rounded-none border text-xs font-bold transition cursor-pointer bg-white ${currentShift.color}`}
          >
            <div className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${currentShift.dot}`} />
              <span>Статус: {currentShift.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-[#555555]">
                {profile.active_slots_count}/{profile.max_slots} слотов
              </span>
              <ChevronDown className="size-3.5" />
            </div>
          </button>

          {/* Shift Dropdown */}
          {isShiftDropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white rounded-none border border-[#dddddd] shadow-lg p-1 z-30 space-y-0.5">
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('active');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-none text-xs font-semibold text-[#1a1a1a] hover:bg-[#e7f8f2] hover:text-[#0d9b68] transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-[#0d9b68]" />
                <span>На линии (принимать тикеты)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('break');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-none text-xs font-semibold text-[#1a1a1a] hover:bg-[#fffbe6] hover:text-[#b7791f] transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-[#fbbd08]" />
                <span>Перерыв (пауза распределения)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onUpdateShift('offline');
                  setIsShiftDropdownOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-none text-xs font-semibold text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
              >
                <span className="size-2 rounded-full bg-[#7f8792]" />
                <span>Не в сети (завершить смену)</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Filter Tabs: Button Group according to section 4.1 */}
      <div className="px-2.5 py-2 flex items-center border-b border-[#e5e5e5] bg-white">
        <div className="flex w-full">
          <button
            type="button"
            onClick={() => setFilterPriority('all')}
            className={`flex-1 py-1.5 text-[11px] font-bold rounded-none transition cursor-pointer text-center border ${
              filterPriority === 'all'
                ? 'bg-[#264b82] text-white border-[#264b82]'
                : 'bg-white text-[#1a1a1a] border-[#dddddd] hover:bg-[#f2f7fc]'
            }`}
          >
            Все ({tickets.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterPriority('P0')}
            className={`flex-1 py-1.5 text-[11px] font-bold rounded-none transition cursor-pointer text-center border -ml-[1px] ${
              filterPriority === 'P0'
                ? 'bg-[#db2b21] text-white border-[#db2b21]'
                : 'bg-white text-[#1a1a1a] border-[#dddddd] hover:bg-[#f2f7fc]'
            }`}
          >
            P0 Срочные
          </button>
          <button
            type="button"
            onClick={() => setFilterPriority('P1')}
            className={`flex-1 py-1.5 text-[11px] font-bold rounded-none transition cursor-pointer text-center border -ml-[1px] ${
              filterPriority === 'P1'
                ? 'bg-[#f67319] text-white border-[#f67319]'
                : 'bg-white text-[#1a1a1a] border-[#dddddd] hover:bg-[#f2f7fc]'
            }`}
          >
            P1
          </button>
        </div>
      </div>

      {/* Ticket List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {filteredTickets.length === 0 ? (
          <div className="py-12 text-center text-xs text-[#7f8792] space-y-2">
            <CheckCircle2 className="size-8 mx-auto text-[#dddddd] stroke-[1.5]" />
            <p className="font-semibold text-[#1a1a1a]">Очередь свободна</p>
            <p className="text-[11px] text-[#7f8792]">Нет назначенных тикетов в выбранной категории</p>
          </div>
        ) : (
          filteredTickets.map((t) => {
            const isSelected = activeTicketId === t.ticket_id;
            const prio = getPriorityBadge(t.priority);

            return (
              <div
                key={t.ticket_id}
                onClick={() => onSelectTicket(t.ticket_id)}
                className={`p-3 border-b border-[#dddddd] transition-colors cursor-pointer select-none rounded-none ${
                  isSelected
                    ? 'bg-[#eaf6ff] border-l-4 border-l-[#264b82]'
                    : 'bg-white hover:bg-[#f2f7fc]'
                }`}
              >
                <div className="flex items-center justify-between gap-1.5 mb-1">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${prio.badge}`}>
                    {prio.label}
                  </span>
                  <div className="flex items-center gap-1 text-[11px] text-[#7f8792]">
                    <Clock className="size-3" />
                    <span>{t.created_at}</span>
                  </div>
                </div>

                <div className="truncate">
                  <span className="text-xs font-bold text-[#1a1a1a] block truncate">
                    {t.company_name || t.client_name || 'Поставщик'}
                  </span>
                  {t.client_name && t.company_name && (
                    <span className="text-[11px] text-[#7f8792] block truncate">
                      {t.client_name}
                    </span>
                  )}
                </div>

                {t.last_message_preview && (
                  <p className="text-[11px] text-[#555555] line-clamp-2 mt-1 leading-relaxed">
                    {t.last_message_preview}
                  </p>
                )}

                <div className="flex items-center justify-between pt-1.5 mt-1.5 border-t border-[#e5e5e5] text-[10px]">
                  <span className="flex items-center gap-1 text-[#7f8792]">
                    <CircleDot className="size-2 text-[#264b82]" />
                    <span className="font-semibold">{t.status === 'in_progress' ? 'В работе' : 'Назначен'}</span>
                  </span>
                  {t.unread_messages_count > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-[#db2b21] text-white font-bold text-[10px]">
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
      <div className="p-2.5 border-t border-[#e5e5e5] bg-[#f7f8f9]">
        <div className="flex items-center justify-between p-2 rounded-none bg-white border border-[#e5e5e5]">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="size-8 rounded-full bg-[#f7f8f9] border border-[#d4d4d5] flex items-center justify-center text-[#264b82] shrink-0 font-bold">
              <User className="size-4" />
            </div>
            <div className="truncate">
              <span className="text-xs font-bold text-[#1a1a1a] block truncate">
                {user?.full_name || profile.full_name}
              </span>
              <span className="text-[10px] text-[#7f8792] block truncate font-semibold">
                Оператор первой линии
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            title="Выйти из аккаунта"
            className="size-7 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#db2b21] hover:bg-[#fef0ef] transition cursor-pointer"
          >
            <LogOut className="size-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
};
