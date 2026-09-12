import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  OperatorProfile,
  OperatorSidebarTicket,
  OperatorTicketWorkspace,
  ShiftStatus,
} from '../../types/operator';
import { UserProfile } from '../../types/auth';
import {
  getOperatorShift,
  updateOperatorShift,
  getOperatorTickets,
  openTicketWorkspace,
  sendOperatorMessage,
  transferTicket,
  resolveOperatorTicket,
  subscribeOperatorEvents,
  mapOperatorMessage,
} from '../../services/operatorApi';
import { OperatorSidebar } from './OperatorSidebar';
import { OperatorChatArea } from './OperatorChatArea';
import { OperatorCopilotPanel } from './OperatorCopilotPanel';
import { TransferModal } from './TransferModal';

interface OperatorWorkspaceProps {
  user: UserProfile | null;
  onLogout: () => void;
  onSwitchToClientMode: () => void;
}

export const OperatorWorkspace: React.FC<OperatorWorkspaceProps> = ({
  user,
  onLogout,
  onSwitchToClientMode,
}) => {
  const [profile, setProfile] = useState<OperatorProfile>({
    user_id: user?.id || 'op-001',
    full_name: user?.full_name || 'Оператор поддержки',
    line_id: 1,
    line_code: 'L1',
    shift_status: 'active',
    max_slots: 5,
    active_slots_count: 0,
  });

  const [tickets, setTickets] = useState<OperatorSidebarTicket[]>([]);
  const [activeTicketId, setActiveTicketId] = useState<string | null>(null);
  const [activeWorkspace, setActiveWorkspace] = useState<OperatorTicketWorkspace | null>(null);
  const [draftText, setDraftText] = useState('');
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isTransferModalOpen, setIsTransferModalOpen] = useState(false);

  // 1. Initial Load: Shift & Tickets
  useEffect(() => {
    const init = async () => {
      try {
        const [loadedProfile, loadedTickets] = await Promise.all([
          getOperatorShift(),
          getOperatorTickets(),
        ]);
        setProfile(loadedProfile);
        setTickets(loadedTickets);

        // Auto-select first ticket if available
        if (loadedTickets.length > 0) {
          setActiveTicketId(loadedTickets[0].ticket_id);
        }
      } catch (err) {
        console.error('Ошибка инициализации АРМ Оператора:', err);
      }
    };
    init();
  }, []);

  // 2. Load Workspace when active ticket changes
  const loadWorkspace = useCallback(async (ticketId: string) => {
    setIsLoadingWorkspace(true);
    try {
      const ws = await openTicketWorkspace(ticketId);
      setActiveWorkspace(ws);
      setDraftText('');
      // Update sidebar ticket status to in_progress and reset unread count
      setTickets((prev) =>
        prev.map((t) =>
          t.ticket_id === ticketId
            ? { ...t, status: 'in_progress', unread_messages_count: 0 }
            : t
        )
      );
    } catch (err) {
      console.error(`Ошибка загрузки тикета ${ticketId}:`, err);
    } finally {
      setIsLoadingWorkspace(false);
    }
  }, []);

  useEffect(() => {
    if (activeTicketId) {
      loadWorkspace(activeTicketId);
    } else {
      setActiveWorkspace(null);
    }
  }, [activeTicketId, loadWorkspace]);

  const activeTicketIdRef = useRef<string | null>(activeTicketId);
  useEffect(() => {
    activeTicketIdRef.current = activeTicketId;
  }, [activeTicketId]);

  // Подписка на Server-Sent Events (SSE) оператора (один постоянный коннект на сессию)
  useEffect(() => {
    const unsubscribe = subscribeOperatorEvents((event, data) => {
      console.log('Operator SSE event received:', event, data);
      const currentActiveId = activeTicketIdRef.current;
      if (event === 'client_message') {
        const mappedMsg = mapOperatorMessage(data);
        if (data.ticket_id === currentActiveId) {
          setActiveWorkspace((prev) => {
            if (!prev || prev.ticket_id !== data.ticket_id) return prev;
            if (prev.messages.some((m) => m.id === mappedMsg.id)) return prev;
            return {
              ...prev,
              messages: [...prev.messages, mappedMsg],
            };
          });
        }
        setTickets((prev) =>
          prev.map((t) =>
            t.ticket_id === data.ticket_id
              ? {
                  ...t,
                  last_message_preview: `Клиент: ${mappedMsg.content.slice(0, 50)}`,
                  unread_messages_count: t.ticket_id === currentActiveId ? 0 : t.unread_messages_count + 1,
                }
              : t
          )
        );
      } else if (event === 'ticket_assigned') {
        getOperatorTickets().then((loaded) => setTickets(loaded));
      } else if (event === 'copilot_ready') {
        if (data.ticket_id === currentActiveId) {
          setActiveWorkspace((prev) => {
            if (!prev || prev.ticket_id !== data.ticket_id) return prev;
            return {
              ...prev,
              copilot_summary: data.copilot_summary || prev.copilot_summary,
            };
          });
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // 3. Shift Status Change
  const handleUpdateShift = async (status: ShiftStatus) => {
    try {
      const updated = await updateOperatorShift(status);
      setProfile(updated);
    } catch (err) {
      console.error('Ошибка обновления статуса смены:', err);
    }
  };

  // 4. Send Message to Client
  const handleSendMessage = async () => {
    if (!activeTicketId || !draftText.trim() || isSendingMessage) return;

    setIsSendingMessage(true);
    try {
      const updatedWs = await sendOperatorMessage(activeTicketId, draftText.trim());
      setActiveWorkspace(updatedWs);
      setDraftText('');

      // Refresh sidebar ticket list preview
      const refreshedTickets = await getOperatorTickets();
      setTickets(refreshedTickets);
    } catch (err) {
      console.error('Ошибка отправки ответа клиенту:', err);
    } finally {
      setIsSendingMessage(false);
    }
  };

  // 5. Transfer Ticket to another Line
  const handleConfirmTransfer = async (targetLineCode: string, comment: string) => {
    if (!activeTicketId) return;

    try {
      await transferTicket(activeTicketId, targetLineCode, comment);

      // Refresh tickets
      const remainingTickets = await getOperatorTickets();
      setTickets(remainingTickets);

      // Select next ticket if available
      if (remainingTickets.length > 0) {
        setActiveTicketId(remainingTickets[0].ticket_id);
      } else {
        setActiveTicketId(null);
        setActiveWorkspace(null);
      }
    } catch (err) {
      console.error('Ошибка перевода тикета:', err);
    }
  };

  // 6. Resolve Ticket
  const handleResolveTicket = async () => {
    if (!activeTicketId) return;

    if (!window.confirm('Вы уверены, что хотите завершить работу по данному обращению?')) {
      return;
    }

    try {
      await resolveOperatorTicket(activeTicketId);

      // Refresh tickets
      const remainingTickets = await getOperatorTickets();
      setTickets(remainingTickets);

      // Select next ticket
      if (remainingTickets.length > 0) {
        setActiveTicketId(remainingTickets[0].ticket_id);
      } else {
        setActiveTicketId(null);
        setActiveWorkspace(null);
      }
    } catch (err) {
      console.error('Ошибка закрытия тикета:', err);
    }
  };

  // 7. Insert AI suggested response
  const handleUseSuggestedResponse = (text: string) => {
    setDraftText(text);
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-white">
      {/* Column 1: Operator Sidebar (Tickets queue & Shift status) */}
      <OperatorSidebar
        profile={profile}
        tickets={tickets}
        activeTicketId={activeTicketId}
        onSelectTicket={(ticketId) => setActiveTicketId(ticketId)}
        onUpdateShift={handleUpdateShift}
        user={user}
        onLogout={onLogout}
        onSwitchToClientMode={onSwitchToClientMode}
      />

      {/* Column 2: Central Chat Workspace */}
      <OperatorChatArea
        workspace={activeWorkspace}
        isLoading={isLoadingWorkspace}
        draftText={draftText}
        onDraftChange={setDraftText}
        onSendMessage={handleSendMessage}
        onTransferClick={() => setIsTransferModalOpen(true)}
        onResolveClick={handleResolveTicket}
        isSending={isSendingMessage}
      />

      {/* Column 3: RAG AI Copilot & Counterparty Details */}
      <OperatorCopilotPanel
        workspace={activeWorkspace}
        onUseSuggestedResponse={handleUseSuggestedResponse}
      />

      {/* Modal: Transfer to L2/L3 */}
      <TransferModal
        isOpen={isTransferModalOpen}
        onClose={() => setIsTransferModalOpen(false)}
        onConfirm={handleConfirmTransfer}
        currentLineCode={profile.line_code}
      />
    </div>
  );
};
