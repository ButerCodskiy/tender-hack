import React, { useState, useEffect } from 'react';
import {
  SquarePen,
  Search,
  PanelLeftClose,
  PanelLeft,
  MessageSquare,
  Sparkles,
  User,
  LogOut,
  LogIn,
  Headphones,
} from 'lucide-react';
import { ChatSession } from '../../types/chat';
import { UserProfile } from '../../types/auth';
import { isStandaloneMode, setStandaloneMode, onModeChange } from '../../config/mode';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onOpenSearch: () => void;
  user: UserProfile | null;
  onOpenAuth: () => void;
  onLogout: () => void;
  onSwitchToOperatorMode?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isCollapsed,
  onToggleCollapse,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onOpenSearch,
  user,
  onOpenAuth,
  onLogout,
  onSwitchToOperatorMode,
}) => {
  const [standalone, setStandalone] = useState(() => isStandaloneMode());

  useEffect(() => {
    return onModeChange((s) => setStandalone(s));
  }, []);

  return (
    <aside
      className={`relative flex flex-col bg-white border-r border-[#e5e5e5] transition-all duration-200 h-full select-none z-30 shrink-0 ${
        isCollapsed ? 'w-16' : 'w-72'
      }`}
    >
      {/* Sidebar Header */}
      <div className="flex items-center px-3.5 h-14 border-b border-[#e5e5e5] shrink-0">
        {/* Toggle Button */}
        <button
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          className="size-9 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition-colors cursor-pointer shrink-0"
        >
          {isCollapsed ? <PanelLeft className="size-5" /> : <PanelLeftClose className="size-5" />}
        </button>

        {/* Branding (visible when expanded) */}
        {!isCollapsed && (
          <div className="flex items-center gap-2.5 overflow-hidden ml-2.5">
            <div className="size-8 rounded-none bg-[#db2b21] flex items-center justify-center text-white shrink-0 font-bold text-xs">
              <Sparkles className="size-4" />
            </div>
            <div className="truncate">
              <span className="font-bold text-[#1a1a1a] text-sm tracking-tight block truncate">
                Портал Поставщиков
              </span>
              <span className="text-[11px] text-[#7f8792] block truncate font-semibold">
                Служба поддержки ЕАИСТ
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Main Navigation Actions */}
      <div className="px-3 py-3 space-y-1.5 border-b border-[#e5e5e5]">
        <button
          onClick={onNewChat}
          className={`flex items-center gap-2.5 w-full rounded-none py-2.5 px-3 text-sm font-bold transition-colors cursor-pointer ${
            !activeSessionId
              ? 'bg-[#db2b21] text-white'
              : 'bg-[#db2b21] hover:bg-[#cd1f15] text-white'
          } ${isCollapsed ? 'justify-center px-0' : ''}`}
        >
          <SquarePen className="size-4.5 shrink-0 text-white" />
          {!isCollapsed && <span>Новый диалог</span>}
        </button>

        <button
          onClick={onOpenSearch}
          className={`flex items-center gap-2.5 w-full rounded-none py-2 px-3 text-xs font-bold text-[#1a1a1a] bg-transparent border border-[#22242626] hover:bg-[#f2f7fc] hover:border-[#22242659] transition-all cursor-pointer ${
            isCollapsed ? 'justify-center px-0' : ''
          }`}
        >
          <Search className="size-4 shrink-0 text-[#7f8792]" />
          {!isCollapsed && <span>Поиск по диалогам</span>}
        </button>

        {onSwitchToOperatorMode && (
          <button
            onClick={onSwitchToOperatorMode}
            title="Перейти в АРМ Оператора поддержки"
            className={`flex items-center gap-2.5 w-full rounded-none py-2 px-3 text-xs font-bold text-white bg-[#264b82] hover:bg-[#1c3f72] transition-colors cursor-pointer ${
              isCollapsed ? 'justify-center px-0' : ''
            }`}
          >
            <Headphones className="size-4 shrink-0 text-white" />
            {!isCollapsed && (
              <span>
                {user?.line_code ? `АРМ Оператора (${user.line_code})` : 'АРМ Оператора'}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Mode Switcher Badge */}
      {!isCollapsed ? (
        <div className="px-3 py-2 border-b border-[#e5e5e5] bg-[#f7f8f9]">
          <div className="flex items-center justify-between p-2 rounded-none bg-white border border-[#e5e5e5] text-xs">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`size-2 rounded-full shrink-0 ${
                  standalone ? 'bg-[#264b82]' : 'bg-[#0d9b68]'
                }`}
              />
              <div className="truncate">
                <span className="text-[11px] font-bold text-[#1a1a1a] block truncate">
                  {standalone ? 'Автономный режим' : 'Режим API (Бэкенд)'}
                </span>
                <span className="text-[10px] text-[#7f8792] block truncate">
                  {standalone ? 'Демо-интерфейс' : 'Сервер подключен'}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setStandaloneMode(!standalone)}
              title={
                standalone
                  ? 'Переключить на реальный бэкенд'
                  : 'Переключить в автономный визуальный режим'
              }
              className="text-[10px] text-[#264b82] hover:text-[#1c3f72] font-bold px-2 py-0.5 rounded-none border border-[#264b82]/30 hover:bg-[#eaf6ff] transition cursor-pointer shrink-0"
            >
              {standalone ? 'К API' : 'В Демо'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex justify-center py-2 border-b border-[#e5e5e5]">
          <button
            type="button"
            onClick={() => setStandaloneMode(!standalone)}
            title={
              standalone
                ? 'Автономный режим (кликните для переключения на API)'
                : 'Режим API (кликните для переключения в Демо)'
            }
            className="p-1 rounded-none hover:bg-[#f2f7fc] transition cursor-pointer"
          >
            <span
              className={`size-2.5 rounded-full inline-block ${
                standalone ? 'bg-[#264b82]' : 'bg-[#0d9b68]'
              }`}
            />
          </button>
        </div>
      )}

      {/* Scrollable Content: History */}
      <div className="flex-1 overflow-y-auto px-2 py-2 custom-scrollbar space-y-4">
        <div>
          {!isCollapsed && (
            <div className="px-2 mb-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#7f8792]">
                История обращений
              </span>
            </div>
          )}

          {sessions.length === 0 ? (
            !isCollapsed && (
              <div className="px-2 py-4 text-center text-xs text-[#7f8792] italic">
                Нет сохраненных обращений
              </div>
            )
          ) : (
            <ul className="space-y-0.5">
              {sessions.map((session) => {
                const isActive = activeSessionId === session.id;
                return (
                  <li key={session.id}>
                    <button
                      onClick={() => onSelectSession(session.id)}
                      title={session.title}
                      className={`flex items-center gap-2.5 w-full rounded-none py-2 px-2.5 text-xs transition-colors cursor-pointer text-left ${
                        isActive
                          ? 'bg-[#eaf6ff] text-[#264b82] border-l-4 border-l-[#264b82] font-bold'
                          : 'text-[#1a1a1a] hover:bg-[#f2f7fc]'
                      } ${isCollapsed ? 'justify-center px-0' : ''}`}
                    >
                      <MessageSquare className="size-3.5 shrink-0 text-[#7f8792]" />
                      {!isCollapsed && (
                        <>
                          <span className="truncate flex-1 text-left text-xs">
                            {session.title}
                          </span>
                          {session.status === 'resolved' && (
                            <span className="size-2 rounded-full bg-[#0d9b68] shrink-0" title="Решено" />
                          )}
                          {session.status === 'escalated_to_operator' && (
                            <span className="size-2 rounded-full bg-[#f67319] shrink-0" title="У оператора" />
                          )}
                          {session.status === 'moderation_closed' && (
                            <span className="size-2 rounded-full bg-[#d32f2f] shrink-0" title="Заблокировано модерацией" />
                          )}
                        </>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* User Profile / Auth Pill at Bottom */}
      <div className="p-2.5 border-t border-[#e5e5e5] bg-[#f7f8f9]">
        {user ? (
          !isCollapsed ? (
            <div className="flex items-center justify-between p-2 rounded-none bg-white border border-[#e5e5e5]">
              <div className="flex items-center gap-2 overflow-hidden min-w-0">
                <div className="size-8 rounded-full bg-[#f7f8f9] border border-[#d4d4d5] flex items-center justify-center text-[#264b82] shrink-0 font-bold">
                  <User className="size-4" />
                </div>
                <div className="truncate min-w-0">
                  <span className="text-xs font-bold text-[#1a1a1a] block truncate">
                    {user.full_name || user.company_name || user.email}
                  </span>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-none bg-[#eaf6ff] text-[#264b82] border border-[#264b82]/30">
                      {user.role_code === 'client'
                        ? 'Поставщик'
                        : user.role_code === 'operator'
                        ? 'Оператор L1'
                        : user.role_code === 'supervisor'
                        ? 'Супервизор'
                        : 'Администратор'}
                    </span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={onLogout}
                aria-label="Выйти из аккаунта"
                title="Выйти из аккаунта"
                className="size-7 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#db2b21] hover:bg-[#fef0ef] transition-colors cursor-pointer shrink-0 ml-1"
              >
                <LogOut className="size-3.5" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1.5">
              <div
                className="size-8 rounded-full bg-[#f7f8f9] border border-[#d4d4d5] flex items-center justify-center text-[#264b82] font-bold"
                title={`${user.full_name || user.email} (${user.role_code})`}
              >
                <User className="size-4" />
              </div>
              <button
                type="button"
                onClick={onLogout}
                aria-label="Выйти"
                title="Выйти из аккаунта"
                className="size-7 rounded-none flex items-center justify-center text-[#7f8792] hover:text-[#db2b21] hover:bg-[#fef0ef] transition-colors cursor-pointer"
              >
                <LogOut className="size-3.5" />
              </button>
            </div>
          )
        ) : (
          !isCollapsed ? (
            <button
              type="button"
              onClick={onOpenAuth}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-none bg-[#db2b21] hover:bg-[#cd1f15] text-white font-bold text-xs transition-colors cursor-pointer"
            >
              <LogIn className="size-4" />
              <span>Войти / Регистрация</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onOpenAuth}
              aria-label="Войти в систему"
              title="Войти в систему"
              className="size-8 mx-auto rounded-none flex items-center justify-center bg-[#db2b21] hover:bg-[#cd1f15] text-white transition-colors cursor-pointer"
            >
              <LogIn className="size-4" />
            </button>
          )
        )}
      </div>
    </aside>
  );
};
