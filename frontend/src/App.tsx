import React, { useState, useRef, useEffect } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { WelcomeScreen } from './components/chat/WelcomeScreen';
import { ChatMessage } from './components/chat/ChatMessage';
import { ChatComposer } from './components/chat/ChatComposer';
import { CsatModal } from './components/chat/CsatModal';
import { SearchModal } from './components/chat/SearchModal';
import { AuthPage } from './components/auth/AuthPage';
import { OperatorWorkspace } from './components/operator/OperatorWorkspace';
import { SupervisorDashboard } from './components/analytics/SupervisorDashboard';
import { ChatSession, Message } from './types/chat';
import { UserProfile } from './types/auth';
import {
  streamChatMessage,
  fetchChatState,
  escalateTicket,
  resolveTicket,
  submitFeedback,
  subscribeChatEvents,
} from './services/api';
import { getStoredUser, clearStoredAuth, fetchCurrentUser, DEMO_USERS } from './services/auth';
import { isStandaloneMode, setStandaloneMode, onModeChange } from './config/mode';
import {
  Sparkles,
  ShieldCheck,
  Headphones,
  UserCheck,
  BarChart3,
  MessageSquare,
} from 'lucide-react';

export const App: React.FC = () => {
  const [standalone, setStandalone] = useState(() => isStandaloneMode());
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(() => getStoredUser());
  const [viewMode, setViewMode] = useState<'client' | 'operator' | 'analytics'>(() => {
    const storedUser = getStoredUser();
    if (storedUser?.role_code === 'supervisor') {
      return 'analytics';
    }
    if (storedUser?.role_code === 'operator' || storedUser?.role_code === 'admin') {
      return 'operator';
    }
    return 'client';
  });

  useEffect(() => {
    return onModeChange((s) => setStandalone(s));
  }, []);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);

  // Состояние активного обращения и оператора
  const [activeTicketId, setActiveTicketId] = useState<string | null>(null);
  const [operatorName, setOperatorName] = useState<string | null>(null);
  const [feedbackTicketId, setFeedbackTicketId] = useState<string | null>(null);

  const [isCsatModalOpen, setIsCsatModalOpen] = useState(false);
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.messages, isSending]);

  // Проверка сессии при монтировании
  useEffect(() => {
    fetchCurrentUser().then((currentUser) => {
      if (currentUser) {
        setUser(currentUser);
        if (currentUser.role_code === 'supervisor') {
          setViewMode('analytics');
        } else if (
          currentUser.role_code === 'operator' ||
          currentUser.role_code === 'admin'
        ) {
          setViewMode('operator');
        } else {
          setViewMode('client');
        }
      } else {
        setUser(null);
      }
    });
  }, [standalone]);

  // Загрузка реального состояния чата с бэкенда при входе клиента
  useEffect(() => {
    if (user && user.role_code === 'client') {
      fetchChatState().then((state) => {
        if (state) {
          if (state.active_ticket) {
            setActiveTicketId(state.active_ticket.id);
            if (state.active_ticket.assigned_operator_name) {
              setOperatorName(state.active_ticket.assigned_operator_name);
            }
          }
          if (state.feedback_ticket_id) {
            setFeedbackTicketId(state.feedback_ticket_id);
          }

          // Группируем сообщения по ticket_id
          const ticketMap = new Map<string, Message[]>();
          const ticketOrder: string[] = [];

          for (const m of state.messages) {
            const tId = m.ticket_id || state.active_ticket?.id || state.chat_id;
            if (!ticketMap.has(tId)) {
              ticketMap.set(tId, []);
              ticketOrder.push(tId);
            }
            const senderName =
              m.sender_name ||
              (m.sender_type === 'operator'
                ? state.active_ticket?.assigned_operator_name || 'Оператор службы поддержки'
                : m.sender_type === 'admin'
                ? 'Администратор Портала'
                : m.sender_type === 'bot'
                ? 'ИИ-Ассистент Портала Поставщиков'
                : undefined);

            const frontendMsg: Message = {
              id: m.id,
              ticket_id: tId,
              content: m.text,
              type:
                m.sender_type === 'client'
                  ? 'user'
                  : m.sender_type === 'system'
                  ? 'system'
                  : 'assistant',
              sender_type: m.sender_type,
              sender_name: senderName,
              sender_role: m.sender_role || m.sender_type,
              timestamp: new Date(m.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              }),
              actions:
                m.sender_type === 'client'
                  ? ['copy', 'edit']
                  : m.sender_type === 'bot'
                  ? ['copy', 'regenerate', 'thumbs_up', 'thumbs_down']
                  : ['copy', 'thumbs_up', 'thumbs_down'],
              needsFeedbackButtons:
                m.sender_type === 'bot' &&
                state.active_ticket?.id === tId &&
                state.active_ticket?.status === 'bot_processing',
              citations: m.sources?.map((s, idx) => ({
                id: s.chunk_id || `c-${idx}`,
                title: s.doc_id || 'Регламент Портала',
                sectionPath: s.doc_id,
                excerpt: s.quote_text,
              })),
            };
            ticketMap.get(tId)!.push(frontendMsg);
          }

          // Если есть активный тикет без сообщений, добавляем его в список
          if (state.active_ticket && !ticketMap.has(state.active_ticket.id)) {
            ticketMap.set(state.active_ticket.id, []);
            ticketOrder.unshift(state.active_ticket.id);
          }

          const loadedSessions: ChatSession[] = ticketOrder.map((tId) => {
            const msgs = ticketMap.get(tId) || [];
            const firstUserMsg = msgs.find((m) => m.type === 'user');
            const title = firstUserMsg
              ? firstUserMsg.content.slice(0, 38) + (firstUserMsg.content.length > 38 ? '...' : '')
              : 'Консультация по регламенту';

            const isActive = state.active_ticket && tId === state.active_ticket.id;
            const status = isActive
              ? state.active_ticket?.status === 'resolved'
                ? 'resolved'
                : state.active_ticket?.status === 'in_progress' ||
                  state.active_ticket?.status === 'assigned'
                ? 'escalated_to_operator'
                : 'active'
              : 'resolved';

            return {
              id: tId,
              title,
              category: 'general',
              createdAt: 'Сегодня',
              updatedAt: new Date().toISOString(),
              status,
              messages: msgs,
            };
          });

          // Сортируем: активный тикет или самый свежий сверху
          if (state.active_ticket) {
            loadedSessions.sort((a, b) =>
              a.id === state.active_ticket?.id ? -1 : b.id === state.active_ticket?.id ? 1 : 0
            );
          }

          setSessions(loadedSessions);

          setActiveSessionId((prev) => {
            if (prev && loadedSessions.some((s) => s.id === prev)) {
              return prev;
            }
            if (state.active_ticket?.id && loadedSessions.some((s) => s.id === state.active_ticket?.id)) {
              return state.active_ticket.id;
            }
            return loadedSessions.length > 0 ? loadedSessions[0].id : null;
          });
        }
      });
    }
  }, [user, standalone]);

  // Подписка на Server-Sent Events (SSE) активного обращения
  useEffect(() => {
    if (!user || user.role_code !== 'client') return;
    if (!activeTicketId) return;

    const unsubscribe = subscribeChatEvents(activeTicketId, (event, data) => {
      console.log('Client SSE event received:', event, data);

      if (event === 'operator_joined') {
        const opName = data.operator_name || 'Специалист поддержки';
        setOperatorName(opName);

        const joinedMessage: Message = {
          id: `op-join-${Date.now()}`,
          content: `К диалогу подключился специалист поддержки: ${opName}`,
          type: 'system',
          sender_type: 'system',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          actions: [],
        };

        const targetTicketId = data.ticket_id || activeTicketId;
        setSessions((prev) =>
          prev.map((s) =>
            !targetTicketId || s.id === targetTicketId
              ? {
                  ...s,
                  status: 'escalated_to_operator',
                  messages: [...s.messages, joinedMessage],
                }
              : s
          )
        );
      } else if (event === 'new_message') {
        const targetTicketId = data.ticket_id || activeTicketId;
        const senderType = data.sender_type || (data.sender_role === 'admin' ? 'admin' : 'operator');
        const senderName =
          data.sender_name ||
          (senderType === 'operator'
            ? operatorName || 'Оператор службы поддержки'
            : senderType === 'admin'
            ? 'Администратор Портала'
            : senderType === 'bot'
            ? 'ИИ-Ассистент Портала Поставщиков'
            : undefined);

        const newMsg: Message = {
          id: data.id || `msg-${Date.now()}`,
          ticket_id: targetTicketId || undefined,
          content: data.text || '',
          type:
            senderType === 'client'
              ? 'user'
              : senderType === 'system'
              ? 'system'
              : 'assistant',
          sender_type: senderType,
          sender_name: senderName,
          sender_role: data.sender_role || senderType,
          timestamp: new Date(data.created_at || Date.now()).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          }),
          actions: senderType === 'client' ? ['copy', 'edit'] : ['copy'],
        };

        setSessions((prev) =>
          prev.map((s) =>
            !targetTicketId || s.id === targetTicketId
              ? {
                  ...s,
                  messages: [...s.messages, newMsg],
                }
              : s
          )
        );
      } else if (event === 'ticket_resolved') {
        const targetTicketId = data.ticket_id || activeTicketId;
        if (data.ticket_id) {
          setFeedbackTicketId(data.ticket_id);
        }
        setSessions((prev) =>
          prev.map((s) =>
            !targetTicketId || s.id === targetTicketId
              ? {
                  ...s,
                  status: 'resolved',
                }
              : s
          )
        );
        setIsCsatModalOpen(true);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [user, activeTicketId]);

  const handleNewChat = () => {
    setActiveSessionId(null);
    setActiveTicketId(null);
    setInputValue('');
  };

  const handleSend = async (customPrompt?: string) => {
    const textToSend = (customPrompt || inputValue).trim();
    if (!textToSend || isSending) return;

    const userMessage: Message = {
      id: `usr-${Date.now()}`,
      content: textToSend,
      type: 'user',
      sender_type: 'client',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      actions: ['copy', 'edit'],
    };

    const botMessageId = `bot-${Date.now()}`;
    const thinkingMessage: Message = {
      id: botMessageId,
      content: '',
      type: 'thinking',
      sender_type: 'bot',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      actions: [],
      statusText: 'Поиск по базе регламентов...',
    };

    let targetSessionId = activeSessionId;
    const isNewChat = !targetSessionId;

    if (!targetSessionId) {
      // Create new session
      const newSessionId = `session-${Date.now()}`;
      targetSessionId = newSessionId;
      const newSession: ChatSession = {
        id: newSessionId,
        title: textToSend.slice(0, 38) + (textToSend.length > 38 ? '...' : ''),
        category: 'general',
        createdAt: 'Сегодня',
        updatedAt: new Date().toISOString(),
        status: 'active',
        messages: [userMessage, thinkingMessage],
      };

      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSessionId);
    } else {
      // Append to active session
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? { ...s, messages: [...s.messages, userMessage, thinkingMessage] }
            : s
        )
      );
    }

    setInputValue('');
    setIsSending(true);

    // Call live SSE / streaming service
    try {
      await streamChatMessage(
        {
          chatId: targetSessionId,
          ticketId: isNewChat ? undefined : targetSessionId,
          newTicket: isNewChat,
          content: textToSend,
        },
        {
          onStatus: (statusText) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id !== targetSessionId) return s;
                return {
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === botMessageId ? { ...m, statusText } : m
                  ),
                };
              })
            );
          },
          onSources: (citations) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id !== targetSessionId) return s;
                return {
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === botMessageId ? { ...m, citations } : m
                  ),
                };
              })
            );
          },
          onChunk: (chunk) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id !== targetSessionId) return s;
                return {
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === botMessageId
                      ? {
                          ...m,
                          type: 'assistant',
                          sender_type: 'bot',
                          isStreaming: true,
                          content: m.content + chunk,
                        }
                      : m
                  ),
                };
              })
            );
          },
          onDone: (fullText, messageId, ticketId) => {
            const resolvedTicketId = ticketId || (isNewChat ? undefined : targetSessionId);
            if (resolvedTicketId) {
              setActiveTicketId(resolvedTicketId);
            }
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id !== targetSessionId && s.id !== resolvedTicketId) return s;
                return {
                  ...s,
                  id: resolvedTicketId || s.id,
                  messages: s.messages.map((m) =>
                    m.id === botMessageId
                      ? {
                          ...m,
                          id: messageId || m.id,
                          ticket_id: resolvedTicketId || m.ticket_id,
                          type: 'assistant',
                          sender_type: 'bot',
                          isStreaming: false,
                          content: fullText || m.content,
                          actions: ['copy', 'regenerate', 'thumbs_up', 'thumbs_down'],
                          needsFeedbackButtons: true,
                        }
                      : { ...m, ticket_id: resolvedTicketId || m.ticket_id }
                  ),
                };
              })
            );
            if (resolvedTicketId && targetSessionId !== resolvedTicketId) {
              setActiveSessionId(resolvedTicketId);
            }
            setIsSending(false);
          },
          onSessionTerminated: (_reason, message) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id !== targetSessionId) return s;
                return {
                  ...s,
                  status: 'moderation_closed',
                  messages: [
                    ...s.messages.filter((m) => m.id !== botMessageId),
                    {
                      id: `mod-${Date.now()}`,
                      content: message || 'Обращение закрыто по правилам регламента.',
                      type: 'system',
                      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                      actions: [],
                    },
                  ],
                };
              })
            );
            setIsSending(false);
          },
        }
      );
    } catch (err: unknown) {
      const errMsg =
        err instanceof Error
          ? err.message
          : 'Произошла непредвиденная ошибка связи с сервисом.';

      if (
        errMsg.includes('Сессия истекла') ||
        errMsg.includes('необходимо войти')
      ) {
        setUser(null);
      }

      const errorMessage: Message = {
        id: `err-${Date.now()}`,
        content: errMsg,
        type: 'system',
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
        actions: [],
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? {
                ...s,
                messages: [
                  ...s.messages.filter((m) => m.id !== botMessageId),
                  errorMessage,
                ],
              }
            : s
        )
      );
    } finally {
      setIsSending(false);
    }
  };

  const handleResolveTicket = async () => {
    let targetTicketId = activeTicketId;
    if (!targetTicketId) {
      const state = await fetchChatState();
      if (state?.active_ticket) {
        targetTicketId = state.active_ticket.id;
        setActiveTicketId(targetTicketId);
      }
    }

    if (targetTicketId) {
      try {
        await resolveTicket(targetTicketId);
        setFeedbackTicketId(targetTicketId);
      } catch (err) {
        console.error('Failed to resolve ticket on backend:', err);
      }
    }

    setIsCsatModalOpen(true);
    if (activeSessionId) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId ? { ...s, status: 'resolved' } : s
        )
      );
    }
  };

  const handleEscalateToOperator = async () => {
    if (!activeSessionId) return;
    if (
      activeSession?.status === 'escalated_to_operator' ||
      activeSession?.status === 'resolved'
    ) {
      return;
    }

    try {
      const summary = await escalateTicket();
      if (summary.id) {
        setActiveTicketId(summary.id);
      }
      if (summary.assigned_operator_name) {
        setOperatorName(summary.assigned_operator_name);
      }
    } catch (err: any) {
      console.warn('Escalation API notice:', err.message || err);
    }

    const operatorMessage: Message = {
      id: `sys-op-${Date.now()}`,
      content:
        'Диалог переведен на профильную линию поддержки («Регламенты и сопровождение процедур»). Оператор подключится в ближайшее время. Слот обращения зафиксирован в очереди.',
      type: 'system',
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      actions: [],
    };

    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSessionId
          ? {
              ...s,
              status: 'escalated_to_operator',
              messages: [...s.messages, operatorMessage],
            }
          : s
      )
    );
  };

  const handleEditMessage = (msgId: string, newContent: string) => {
    if (!activeSessionId) return;

    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== activeSessionId) return s;
        return {
          ...s,
          messages: s.messages.map((m) =>
            m.id === msgId ? { ...m, content: newContent } : m
          ),
        };
      })
    );

    handleSend(newContent);
  };

  const handleQuickSwitchRole = (mode: 'client' | 'operator' | 'analytics') => {
    setViewMode(mode);
    if (!user) {
      const demoRole = mode === 'analytics' ? 'supervisor' : mode === 'operator' ? 'operator' : 'client';
      const demoUser = DEMO_USERS.find((u) => u.role === demoRole);
      if (demoUser) {
        const dummyProfile: UserProfile = {
          id: `demo-${demoUser.role}`,
          role_code: demoUser.role,
          email: demoUser.email,
          full_name: demoUser.name,
          company_name: demoUser.company,
          inn: demoUser.inn,
        };
        setUser(dummyProfile);
        try {
          localStorage.setItem('portal_auth_user', JSON.stringify(dummyProfile));
        } catch {}
      }
    }
  };

  const renderDemoHeader = () => (
    <header className="bg-[#002b54] text-white px-3 sm:px-6 py-2 flex items-center justify-between border-b border-[#003870] shadow-sm shrink-0 z-40 select-none">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="bg-[#db2b21] text-white text-[10px] font-black px-1.5 py-0.5 uppercase tracking-wider">
            ЕАИСТ
          </span>
          <span className="font-bold text-xs tracking-tight text-white hidden md:inline">
            Портал Поставщиков Москвы
          </span>
        </div>
        <span className="text-white/30 hidden sm:inline">•</span>
        <span className="text-[11px] font-medium text-white/70 hidden lg:inline">
          АРМ Техподдержки
        </span>
      </div>

      {/* Role / View Mode Switcher */}
      <nav className="flex items-center bg-[#001c38] p-1 rounded-sm border border-[#004B87]/60 gap-1 shadow-inner">
        <button
          type="button"
          onClick={() => handleQuickSwitchRole('client')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-sm transition cursor-pointer ${
            viewMode === 'client'
              ? 'bg-[#004B87] text-white shadow-sm ring-1 ring-white/20'
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
          title="Интерфейс пользователя / поставщика (Чат с ботом и эскалация)"
        >
          <MessageSquare className="size-3.5 text-white/90" />
          <span>Клиент</span>
        </button>

        <button
          type="button"
          onClick={() => handleQuickSwitchRole('operator')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-sm transition cursor-pointer ${
            viewMode === 'operator'
              ? 'bg-[#004B87] text-white shadow-sm ring-1 ring-white/20'
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
          title="Рабочее место оператора L2 с AI Copilot"
        >
          <Headphones className="size-3.5 text-white/90" />
          <span>Оператор L2</span>
        </button>

        <button
          type="button"
          onClick={() => handleQuickSwitchRole('analytics')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-sm transition cursor-pointer ${
            viewMode === 'analytics'
              ? 'bg-[#004B87] text-white shadow-sm ring-1 ring-white/20'
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
          title="Дашборд руководителя, Adjusted CSAT и инциденты"
        >
          <BarChart3 className="size-3.5 text-white/90" />
          <span>Дашборд руководителя</span>
        </button>
      </nav>

      {/* Right controls: API toggle & current user */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setStandaloneMode(!standalone)}
          title={
            standalone
              ? 'Автономный режим (UI Mock). Кликните для переключения на бэкенд API.'
              : 'Режим связи с бэкендом (API). Кликните для переключения в Демо.'
          }
          className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[10px] font-bold border transition cursor-pointer hover:opacity-90 ${
            standalone
              ? 'bg-[#eaf6ff] text-[#264b82] border-[#264b82]/40'
              : 'bg-[#e7f8f2] text-[#0d9b68] border-[#0d9b68]/40'
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${
              standalone ? 'bg-[#264b82]' : 'bg-[#0d9b68]'
            }`}
          />
          <span>{standalone ? 'Автономный' : 'API'}</span>
        </button>

        {user && (
          <div className="hidden xl:flex items-center gap-2 text-xs text-white/80">
            <span className="size-2 rounded-full bg-[#0d9b68]" />
            <span className="truncate max-w-[150px] font-medium">
              {user.full_name || user.email}
            </span>
          </div>
        )}
      </div>
    </header>
  );

  // Обязательный экран авторизации для неавторизованных посетителей
  if (!user) {
    return (
      <div className="h-dvh w-full flex flex-col overflow-hidden bg-[#f7f8f9]">
        {renderDemoHeader()}
        <div className="flex-1 overflow-hidden">
          <AuthPage
            onSuccess={(authedUser) => {
              setUser(authedUser);
              if (authedUser.role_code === 'supervisor') {
                setViewMode('analytics');
              } else if (
                authedUser.role_code === 'operator' ||
                authedUser.role_code === 'admin'
              ) {
                setViewMode('operator');
              } else {
                setViewMode('client');
              }
            }}
          />
        </div>
      </div>
    );
  }

  if (viewMode === 'analytics') {
    return (
      <div className="h-dvh w-full flex flex-col overflow-hidden bg-[#F5F6F8]">
        {renderDemoHeader()}
        <div className="flex-1 overflow-hidden">
          <SupervisorDashboard onBackToOperator={() => setViewMode('operator')} />
        </div>
      </div>
    );
  }

  if (viewMode === 'operator') {
    return (
      <div className="h-dvh w-full flex flex-col overflow-hidden">
        {renderDemoHeader()}
        <div className="flex-1 overflow-hidden">
          <OperatorWorkspace
            user={user}
            onLogout={() => {
              clearStoredAuth();
              setUser(null);
              setViewMode('client');
            }}
            onSwitchToClientMode={() => setViewMode('client')}
          />
        </div>
        {isAuthOpen && (
          <AuthPage
            onSuccess={(authedUser) => {
              setUser(authedUser);
              setIsAuthOpen(false);
              if (authedUser.role_code === 'supervisor') {
                setViewMode('analytics');
              } else if (authedUser.role_code === 'operator' || authedUser.role_code === 'admin') {
                setViewMode('operator');
              } else {
                setViewMode('client');
              }
            }}
            onCancel={() => setIsAuthOpen(false)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-dvh w-full bg-[#f7f8f9] text-[#1a1a1a] font-sans overflow-hidden">
      {renderDemoHeader()}
      <div className="flex flex-1 h-[calc(100%-41px)] overflow-hidden">
        {/* Collapsible Sidebar */}
        <Sidebar
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={(id) => {
            setActiveSessionId(id);
            setActiveTicketId(id);
          }}
          onNewChat={handleNewChat}
          onOpenSearch={() => setIsSearchModalOpen(true)}
          user={user}
          onOpenAuth={() => setIsAuthOpen(true)}
          onLogout={() => {
            clearStoredAuth();
            setUser(null);
          }}
          onSwitchToOperatorMode={
            user?.role_code === 'operator' || user?.role_code === 'supervisor' || user?.role_code === 'admin'
              ? () => setViewMode('operator')
              : undefined
          }
        />

      {/* Main Workspace Container */}
      <main className="flex-1 flex flex-col h-full overflow-hidden p-0 md:p-2 bg-[#f7f8f9]">
        <div className="flex-1 flex flex-col bg-white rounded-none border border-[#e5e5e5] overflow-hidden relative shadow-none">
          {/* Top Bar for active chat */}
          {activeSession && (
            <header className="px-5 py-3 border-b border-[#e5e5e5] flex items-center justify-between shrink-0 bg-white z-10">
              <div className="flex items-center gap-3 overflow-hidden">
                <div className="size-8 rounded-none bg-[#fef0ef] text-[#db2b21] border border-[#db2b21]/20 flex items-center justify-center shrink-0">
                  <Sparkles className="size-4" />
                </div>
                <div className="truncate">
                  <h2 className="text-sm font-bold text-[#1a1a1a] truncate">
                    {activeSession.title}
                  </h2>
                  <div className="flex items-center gap-2 text-xs text-[#7f8792]">
                    <span className="flex items-center gap-1 font-medium">
                      <ShieldCheck className="size-3 text-[#0d9b68]" />
                      {activeSession.status === 'resolved'
                        ? 'Вопрос решен'
                        : activeSession.status === 'escalated_to_operator'
                        ? 'На линии оператора'
                        : 'ИИ-Консультация активна'}
                    </span>
                    <span>•</span>
                    <span>{activeSession.messages.length} сообщений</span>
                  </div>
                </div>
              </div>

              {/* Mode & Status Actions in header */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStandaloneMode(!standalone)}
                  title={
                    standalone
                      ? 'Автономный режим (UI Mock). Кликните для переключения на бэкенд API.'
                      : 'Режим связи с бэкендом (API). Кликните для переключения в Демо.'
                  }
                  className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-none text-[11px] font-bold border transition cursor-pointer hover:opacity-90 ${
                    standalone
                      ? 'bg-[#eaf6ff] text-[#264b82] border-[#264b82]/30'
                      : 'bg-[#e7f8f2] text-[#0d9b68] border-[#0d9b68]/30'
                  }`}
                >
                  <span
                    className={`size-1.5 rounded-full ${
                      standalone ? 'bg-[#264b82]' : 'bg-[#0d9b68]'
                    }`}
                  />
                  <span>{standalone ? 'Автономный' : 'API'}</span>
                </button>

                {activeSession.status === 'active' && (
                  <button
                    type="button"
                    onClick={handleEscalateToOperator}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-[#264b82] bg-transparent hover:bg-[#eaf6ff] border border-[#264b82] transition cursor-pointer"
                  >
                    <Headphones className="size-3.5 text-[#264b82]" />
                    <span className="hidden sm:inline">Вызвать оператора</span>
                  </button>
                )}

                {activeSession.status === 'escalated_to_operator' && (
                  operatorName ? (
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#e7f8f2] text-[#0d9b68] border border-[#0d9b68]/30">
                      <UserCheck className="size-3.5 text-[#0d9b68]" />
                      <span>Специалист: <strong>{operatorName}</strong></span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#fffbe6] text-[#b7791f] border border-[#fbbd08]/40">
                      <Headphones className="size-3.5 text-[#b7791f]" />
                      <span>В очереди к оператору</span>
                    </div>
                  )
                )}
              </div>
            </header>
          )}

          {/* Connected Operator Banner inside chat */}
          {activeSession && operatorName && activeSession.status === 'escalated_to_operator' && (
            <div className="bg-[#eaf6ff] border-b border-[#b9dbf7] px-5 py-2 flex items-center justify-between text-xs text-[#1a1a1a]">
              <div className="flex items-center gap-2">
                <UserCheck className="size-4 text-[#264b82]" />
                <span>К вашему диалогу подключен специалист службы поддержки: <strong className="text-[#264b82]">{operatorName}</strong></span>
              </div>
              <span className="text-[11px] text-[#264b82] font-bold">Линия L1</span>
            </div>
          )}

          {/* Body Content Area */}
          {!activeSession || activeSession.messages.length === 0 ? (
            <WelcomeScreen
              inputValue={inputValue}
              onInputChange={setInputValue}
              onSend={() => handleSend()}
              isSending={isSending}
              onSelectQuickPrompt={(prompt) => {
                setInputValue(prompt);
                handleSend(prompt);
              }}
            />
          ) : (
            <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#f7f8f9]">
              {/* Messages Scroll Area */}
              <div className="flex-1 overflow-y-auto px-4 md:px-8 py-5 custom-scrollbar space-y-3">
                <div className="w-full max-w-4xl mx-auto space-y-3 min-w-0">
                  {activeSession.messages.map((message) => (
                    <ChatMessage
                      key={message.id}
                      message={message}
                      onEditMessage={handleEditMessage}
                      onRegenerate={() => handleSend(message.content)}
                      onResolveTicket={handleResolveTicket}
                      onEscalateToOperator={handleEscalateToOperator}
                      isEscalated={activeSession.status === 'escalated_to_operator'}
                    />
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Sticky Bottom Composer */}
              <div className="p-3 border-t border-[#e5e5e5] bg-white">
                <ChatComposer
                  variant="bottom"
                  inputValue={inputValue}
                  onInputChange={setInputValue}
                  onSend={() => handleSend()}
                  isSending={isSending}
                />
              </div>
            </div>
          )}
        </div>
      </main>
      </div>

      {/* CSAT Modal */}
      <CsatModal
        isOpen={isCsatModalOpen}
        onClose={() => setIsCsatModalOpen(false)}
        onSubmit={async (score, comment, category) => {
          const targetTicketId = feedbackTicketId || activeTicketId;
          if (targetTicketId) {
            try {
              await submitFeedback(
                targetTicketId,
                score,
                comment || (category ? `Категория: ${category}` : undefined)
              );
              setFeedbackTicketId(null);
            } catch (err) {
              console.error('Failed to submit feedback to backend:', err);
            }
          }
        }}
      />

      {/* Search Modal */}
      <SearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
        sessions={sessions}
        onSelectSession={(id) => setActiveSessionId(id)}
      />

      {/* Auth Modal / Page */}
      {isAuthOpen && (
        <AuthPage
          onSuccess={(authedUser) => {
            setUser(authedUser);
            setIsAuthOpen(false);
            if (authedUser.role_code === 'supervisor') {
              setViewMode('analytics');
            } else if (authedUser.role_code === 'operator' || authedUser.role_code === 'admin') {
              setViewMode('operator');
            } else {
              setViewMode('client');
            }
          }}
          onCancel={() => setIsAuthOpen(false)}
        />
      )}
    </div>
  );
};
