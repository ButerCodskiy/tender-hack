import React from 'react';
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
  return (
    <aside
      className={`relative flex flex-col bg-white border-r border-gray-100 transition-all duration-300 h-dvh select-none z-30 shrink-0 ${
        isCollapsed ? 'w-16' : 'w-72'
      }`}
    >
      {/* Sidebar Header */}
      <div className="flex items-center px-3.5 h-16 border-b border-gray-100 shrink-0">
        {/* Toggle Button - always at the exact same physical coordinates */}
        <button
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          className="size-9 rounded-xl flex items-center justify-center text-text-100 hover:text-title-50 hover:bg-background-soft-100 transition-colors cursor-pointer shrink-0"
        >
          {isCollapsed ? <PanelLeft className="size-5" /> : <PanelLeftClose className="size-5" />}
        </button>

        {/* Branding (visible when expanded) */}
        {!isCollapsed && (
          <div className="flex items-center gap-2.5 overflow-hidden ml-2.5">
            <div className="size-8 rounded-lg bg-gradient-to-tr from-primary-600 to-primary-400 flex items-center justify-center text-white shadow-xs shrink-0">
              <Sparkles className="size-4" />
            </div>
            <div className="truncate">
              <span className="font-semibold text-title-50 text-sm tracking-tight block truncate">
                Портал Поставщиков
              </span>
              <span className="text-[11px] text-text-100 block truncate font-medium">
                AI Поддержка
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Main Navigation Actions */}
      <div className="px-3 py-3 space-y-1">
        <button
          onClick={onNewChat}
          className={`flex items-center gap-3 w-full rounded-xl py-2.5 px-3 font-medium text-sm transition-all cursor-pointer ${
            !activeSessionId
              ? 'bg-primary-50 text-primary-600 font-semibold'
              : 'text-text-200 hover:bg-background-soft-100 hover:text-title-50'
          } ${isCollapsed ? 'justify-center px-0' : ''}`}
        >
          <SquarePen className="size-5 shrink-0 text-primary-500" />
          {!isCollapsed && <span>Новый диалог</span>}
        </button>

        <button
          onClick={onOpenSearch}
          className={`flex items-center gap-3 w-full rounded-xl py-2.5 px-3 font-medium text-sm text-text-100 hover:bg-background-soft-100 hover:text-title-50 transition-all cursor-pointer ${
            isCollapsed ? 'justify-center px-0' : ''
          }`}
        >
          <Search className="size-5 shrink-0" />
          {!isCollapsed && <span>Поиск по диалогам</span>}
        </button>

        {onSwitchToOperatorMode && (
          <button
            onClick={onSwitchToOperatorMode}
            title="Перейти в АРМ Оператора поддержки"
            className={`flex items-center gap-3 w-full rounded-xl py-2.5 px-3 font-medium text-sm text-indigo-700 bg-indigo-50/70 hover:bg-indigo-100/80 transition-all cursor-pointer border border-indigo-100 ${
              isCollapsed ? 'justify-center px-0' : ''
            }`}
          >
            <Headphones className="size-5 shrink-0 text-indigo-600" />
            {!isCollapsed && <span className="font-semibold">АРМ Оператора</span>}
          </button>
        )}
      </div>

      {/* Scrollable Content: History */}
      <div className="flex-1 overflow-y-auto px-3 py-2 custom-scrollbar space-y-6">
        {/* Chat History */}
        <div>
          {!isCollapsed && (
            <div className="px-3 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                История обращений
              </span>
            </div>
          )}

          {sessions.length === 0 ? (
            !isCollapsed && (
              <div className="px-3 py-4 text-center text-xs text-gray-400 italic">
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
                      className={`flex items-center gap-2.5 w-full rounded-xl py-2 px-3 text-sm transition-all cursor-pointer ${
                        isActive
                          ? 'bg-background-soft-100 text-title-50 font-medium'
                          : 'text-text-100 hover:bg-background-soft-50 hover:text-title-50'
                      } ${isCollapsed ? 'justify-center px-0' : ''}`}
                    >
                      <MessageSquare className="size-4 shrink-0 text-gray-400" />
                      {!isCollapsed && (
                        <>
                          <span className="truncate flex-1 text-left text-xs">
                            {session.title}
                          </span>
                          {session.status === 'resolved' && (
                            <span className="size-2 rounded-full bg-emerald-500 shrink-0" title="Решено" />
                          )}
                          {session.status === 'escalated_to_operator' && (
                            <span className="size-2 rounded-full bg-amber-500 shrink-0" title="У оператора" />
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
      <div className="p-3 border-t border-gray-100">
        {user ? (
          !isCollapsed ? (
            <div className="flex items-center justify-between p-2 rounded-2xl bg-gradient-to-r from-gray-50 via-primary-50/20 to-primary-100/30 border border-gray-100">
              <div className="flex items-center gap-2.5 overflow-hidden min-w-0">
                <div className="size-9 rounded-full bg-white border border-gray-200 flex items-center justify-center text-primary-600 shrink-0 font-semibold shadow-2xs">
                  <User className="size-4.5" />
                </div>
                <div className="truncate min-w-0">
                  <span className="text-xs font-semibold text-title-50 block truncate">
                    {user.full_name || user.company_name || user.email}
                  </span>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-primary-100/70 text-primary-700 border border-primary-200/50">
                      {user.role_code === 'client'
                        ? 'Поставщик'
                        : user.role_code === 'operator'
                        ? 'Оператор 1-й линии'
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
                className="size-8 rounded-xl flex items-center justify-center text-text-100 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer shrink-0 ml-1"
              >
                <LogOut className="size-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1.5">
              <div
                className="size-9 rounded-full bg-white border border-gray-200 flex items-center justify-center text-primary-600 font-semibold shadow-2xs"
                title={`${user.full_name || user.email} (${user.role_code})`}
              >
                <User className="size-4.5" />
              </div>
              <button
                type="button"
                onClick={onLogout}
                aria-label="Выйти"
                title="Выйти из аккаунта"
                className="size-7 rounded-lg flex items-center justify-center text-text-100 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer"
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
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-2xl bg-primary-600 hover:bg-primary-700 text-white font-medium text-xs shadow-xs transition-colors cursor-pointer"
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
              className="size-9 mx-auto rounded-xl flex items-center justify-center bg-primary-600 hover:bg-primary-700 text-white transition-colors cursor-pointer shadow-xs"
            >
              <LogIn className="size-4.5" />
            </button>
          )
        )}
      </div>
    </aside>
  );
};
