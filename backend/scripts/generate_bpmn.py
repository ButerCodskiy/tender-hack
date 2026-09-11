"""Скрипт генерации чистого и валидного BPMN 2.0 XML с префиксами bpmn, bpmndi, dc, di."""

import xml.etree.ElementTree as ET
from collections import defaultdict
from xml.dom import minidom

NS_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
NS_DI = "http://www.omg.org/spec/DD/20100524/DI"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("bpmn", NS_BPMN)
ET.register_namespace("bpmndi", NS_BPMNDI)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("di", NS_DI)
ET.register_namespace("xsi", NS_XSI)


def create_bpmn() -> str:
    root = ET.Element(
        f"{{{NS_BPMN}}}definitions",
        {
            "id": "Definitions_SupportProcess",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "exporter": "StormBPMN Generator",
            "exporterVersion": "2.0",
        },
    )

    # 1. Коллаборация
    collaboration = ET.SubElement(
        root, f"{{{NS_BPMN}}}collaboration", {"id": "Collaboration_Support"}
    )
    ET.SubElement(
        collaboration,
        f"{{{NS_BPMN}}}participant",
        {
            "id": "Participant_SupportProcess",
            "name": "Сквозной процесс технической поддержки (RAG + АРМ Оператора)",
            "processRef": "Process_Support",
        },
    )

    # 2. Процесс
    process = ET.SubElement(
        root,
        f"{{{NS_BPMN}}}process",
        {"id": "Process_Support", "isExecutable": "true"},
    )

    lane_set = ET.SubElement(
        process, f"{{{NS_BPMN}}}laneSet", {"id": "LaneSet_Support"}
    )

    lanes_def = [
        ("Lane_Client", "Клиент (Пользователь)", 80, 160),
        ("Lane_Chat", "Сервис диалогов (chat)", 240, 160),
        ("Lane_RAG", "Поисково-генеративное ядро (rag)", 400, 180),
        ("Lane_Operators", "Диспетчер очередей и задач (operators)", 580, 180),
        ("Lane_OperatorARM", "Специалист поддержки (АРМ)", 760, 160),
        ("Lane_Analytics", "Контроль качества и аудит (analytics)", 920, 160),
    ]

    lanes_nodes: dict[str, list[str]] = {
        lane_id: [] for lane_id, _, _, _ in lanes_def
    }

    # Элементы процесса
    nodes = [
        # --- Дорожка Клиента ---
        (
            "Start_ClientQuestion",
            "startEvent",
            "Возник вопрос",
            "Lane_Client",
            (220, 142, 36, 36),
        ),
        (
            "Task_ClientSendMessage",
            "userTask",
            "Отправка сообщения в чат",
            "Lane_Client",
            (290, 120, 120, 80),
        ),
        (
            "Task_ClientReceiveResponse",
            "userTask",
            "Получение ответа и ознакомление",
            "Lane_Client",
            (1600, 120, 130, 80),
        ),
        (
            "Task_ClientFeedback",
            "userTask",
            "Оценка качества ответа",
            "Lane_Client",
            (1780, 120, 120, 80),
        ),
        (
            "End_ClientSuccess",
            "endEvent",
            "Вопрос решен",
            "Lane_Client",
            (1950, 142, 36, 36),
        ),
        (
            "End_ClientAbuse",
            "endEvent",
            "Диалог заблокирован за мат",
            "Lane_Client",
            (620, 142, 36, 36),
        ),
        # --- Дорожка Chat ---
        (
            "Task_CheckProfanity",
            "serviceTask",
            "Проверка на ненормативную лексику",
            "Lane_Chat",
            (290, 280, 120, 80),
        ),
        (
            "Gateway_Profanity",
            "exclusiveGateway",
            "Лексика в норме?",
            "Lane_Chat",
            (460, 295, 50, 50),
        ),
        (
            "Task_CloseAbuse",
            "serviceTask",
            "Завершение сессии и отправка предупреждения",
            "Lane_Chat",
            (560, 250, 130, 70),
        ),
        (
            "Task_SaveContext",
            "serviceTask",
            "Сохранение реплики в БД и контекста в Redis",
            "Lane_Chat",
            (560, 330, 130, 70),
        ),
        (
            "Task_SendStreamResponse",
            "serviceTask",
            "Передача ответа клиенту потоком SSE",
            "Lane_Chat",
            (1600, 280, 130, 80),
        ),
        # --- Дорожка RAG ---
        (
            "Task_RouteQuery",
            "serviceTask",
            "Классификация темы, приоритета и линии",
            "Lane_RAG",
            (730, 450, 130, 80),
        ),
        (
            "Task_HybridSearch",
            "serviceTask",
            "Двухканальный поиск и Cross-Encoder реранк",
            "Lane_RAG",
            (900, 450, 130, 80),
        ),
        (
            "Gateway_Confidence",
            "exclusiveGateway",
            "Оценка релевантности?",
            "Lane_RAG",
            (1070, 465, 50, 50),
        ),
        (
            "Task_FaqFastPath",
            "serviceTask",
            "Быстрый ответ типового решения FAQ",
            "Lane_RAG",
            (1170, 410, 130, 70),
        ),
        (
            "Task_AssembleContext",
            "serviceTask",
            "Сборка контекста по AST и связям",
            "Lane_RAG",
            (1170, 490, 130, 70),
        ),
        (
            "Task_GenerateAnswer",
            "serviceTask",
            "Потоковая генерация ответа со сносками",
            "Lane_RAG",
            (1330, 490, 130, 70),
        ),
        (
            "Task_VerifySlots",
            "serviceTask",
            "Инлайн-проверка числовых слотов",
            "Lane_RAG",
            (1480, 490, 110, 70),
        ),
        # --- Дорожка Очередей и Диспетчера ---
        (
            "Task_EnqueueTicket",
            "serviceTask",
            "Постановка тикета в очередь линии в Redis",
            "Lane_Operators",
            (1030, 630, 130, 80),
        ),
        (
            "Gateway_ForkEscalation",
            "parallelGateway",
            "Параллельная обработка",
            "Lane_Operators",
            (1190, 645, 50, 50),
        ),
        (
            "Task_CopilotSummary",
            "serviceTask",
            "Фоновая генерация сводки и подбор статей",
            "Lane_Operators",
            (1270, 600, 130, 60),
        ),
        (
            "Task_BalanceSlots",
            "serviceTask",
            "Балансировка и захват слота оператора",
            "Lane_Operators",
            (1270, 680, 130, 60),
        ),
        (
            "Gateway_JoinEscalation",
            "parallelGateway",
            "Синхронизация задач",
            "Lane_Operators",
            (1430, 645, 50, 50),
        ),
        (
            "Task_NotifyOperator",
            "serviceTask",
            "Оповещение АРМ оператора через брокер",
            "Lane_Operators",
            (1510, 630, 130, 80),
        ),
        # --- Дорожка Оператора ---
        (
            "Task_OperatorConsult",
            "userTask",
            "Консультация клиента в диалоге",
            "Lane_OperatorARM",
            (1600, 800, 130, 80),
        ),
        (
            "Gateway_NewKnowledge",
            "exclusiveGateway",
            "Решение уникально?",
            "Lane_OperatorARM",
            (1770, 815, 50, 50),
        ),
        (
            "Task_SubmitFaqDraft",
            "serviceTask",
            "Отправка пары вопрос-ответ на модерацию FAQ",
            "Lane_OperatorARM",
            (1860, 770, 130, 70),
        ),
        (
            "Task_ResolveTicket",
            "serviceTask",
            "Перевод тикета в статус resolved",
            "Lane_OperatorARM",
            (1860, 850, 130, 60),
        ),
        # --- Дорожка Аналитики ---
        (
            "Gateway_AnalyticsTrigger",
            "exclusiveGateway",
            "Событие аудита",
            "Lane_Analytics",
            (1780, 975, 50, 50),
        ),
        (
            "Task_AuditQuality",
            "serviceTask",
            "Автоматический аудит диалога нейросетью",
            "Lane_Analytics",
            (1860, 960, 130, 80),
        ),
        (
            "Gateway_IncidentCheck",
            "exclusiveGateway",
            "Сбой платформы?",
            "Lane_Analytics",
            (2020, 975, 50, 50),
        ),
        (
            "Task_LogIncident",
            "serviceTask",
            "Фиксация системного сбоя в реестре",
            "Lane_Analytics",
            (2090, 930, 120, 60),
        ),
        (
            "End_AuditCompleted",
            "endEvent",
            "Обращение проверено",
            "Lane_Analytics",
            (2140, 1002, 36, 36),
        ),
    ]

    for n in nodes:
        lanes_nodes[n[3]].append(n[0])

    flows = [
        # Клиент -> Chat
        (
            "Flow_1",
            "Start_ClientQuestion",
            "Task_ClientSendMessage",
            None,
            [(256, 160), (290, 160)],
        ),
        (
            "Flow_2",
            "Task_ClientSendMessage",
            "Task_CheckProfanity",
            None,
            [(350, 200), (350, 280)],
        ),
        # Модерация
        (
            "Flow_3",
            "Task_CheckProfanity",
            "Gateway_Profanity",
            None,
            [(410, 320), (460, 320)],
        ),
        (
            "Flow_4_Abuse",
            "Gateway_Profanity",
            "Task_CloseAbuse",
            "Нарушение",
            [(485, 295), (485, 285), (560, 285)],
        ),
        (
            "Flow_5_AbuseEnd",
            "Task_CloseAbuse",
            "End_ClientAbuse",
            None,
            [(625, 250), (625, 178)],
        ),
        (
            "Flow_6_Clean",
            "Gateway_Profanity",
            "Task_SaveContext",
            "Норма",
            [(485, 345), (485, 365), (560, 365)],
        ),
        # Chat -> RAG
        (
            "Flow_7",
            "Task_SaveContext",
            "Task_RouteQuery",
            None,
            [(690, 365), (710, 365), (710, 490), (730, 490)],
        ),
        (
            "Flow_8",
            "Task_RouteQuery",
            "Task_HybridSearch",
            None,
            [(860, 490), (900, 490)],
        ),
        (
            "Flow_9",
            "Task_HybridSearch",
            "Gateway_Confidence",
            None,
            [(1030, 490), (1070, 490)],
        ),
        # RAG ветвление
        (
            "Flow_10_Faq",
            "Gateway_Confidence",
            "Task_FaqFastPath",
            "Типовой FAQ",
            [(1095, 465), (1095, 445), (1170, 445)],
        ),
        (
            "Flow_11_High",
            "Gateway_Confidence",
            "Task_AssembleContext",
            "Высокий скор",
            [(1095, 515), (1095, 525), (1170, 525)],
        ),
        (
            "Flow_12_RAGGen",
            "Task_AssembleContext",
            "Task_GenerateAnswer",
            None,
            [(1300, 525), (1330, 525)],
        ),
        (
            "Flow_13_Verify",
            "Task_GenerateAnswer",
            "Task_VerifySlots",
            None,
            [(1460, 525), (1480, 525)],
        ),
        (
            "Flow_14_FaqToSend",
            "Task_FaqFastPath",
            "Task_SendStreamResponse",
            None,
            [(1300, 445), (1560, 445), (1560, 320), (1600, 320)],
        ),
        (
            "Flow_15_GenToSend",
            "Task_VerifySlots",
            "Task_SendStreamResponse",
            None,
            [(1590, 525), (1665, 525), (1665, 360)],
        ),
        # Ответ -> Клиент
        (
            "Flow_16_ToClient",
            "Task_SendStreamResponse",
            "Task_ClientReceiveResponse",
            "SSE поток",
            [(1665, 280), (1665, 200)],
        ),
        (
            "Flow_17_ToFeedback",
            "Task_ClientReceiveResponse",
            "Task_ClientFeedback",
            None,
            [(1730, 160), (1780, 160)],
        ),
        (
            "Flow_18_ClientDone",
            "Task_ClientFeedback",
            "End_ClientSuccess",
            None,
            [(1900, 160), (1950, 160)],
        ),
        # Эскалация к оператору
        (
            "Flow_19_Escalate",
            "Gateway_Confidence",
            "Task_EnqueueTicket",
            "Низкий скор / вызов",
            [(1095, 515), (1095, 630)],
        ),
        (
            "Flow_20_Fork",
            "Task_EnqueueTicket",
            "Gateway_ForkEscalation",
            None,
            [(1160, 670), (1190, 670)],
        ),
        (
            "Flow_21_Copilot",
            "Gateway_ForkEscalation",
            "Task_CopilotSummary",
            None,
            [(1215, 645), (1215, 630), (1270, 630)],
        ),
        (
            "Flow_22_Balance",
            "Gateway_ForkEscalation",
            "Task_BalanceSlots",
            None,
            [(1215, 695), (1215, 710), (1270, 710)],
        ),
        (
            "Flow_23_CopilotJoin",
            "Task_CopilotSummary",
            "Gateway_JoinEscalation",
            None,
            [(1400, 630), (1455, 630), (1455, 645)],
        ),
        (
            "Flow_24_BalanceJoin",
            "Task_BalanceSlots",
            "Gateway_JoinEscalation",
            None,
            [(1400, 710), (1455, 710), (1455, 695)],
        ),
        (
            "Flow_25_Notify",
            "Gateway_JoinEscalation",
            "Task_NotifyOperator",
            None,
            [(1480, 670), (1510, 670)],
        ),
        # Диспетчер -> Оператор
        (
            "Flow_26_ToOperator",
            "Task_NotifyOperator",
            "Task_OperatorConsult",
            "Назначен слот",
            [(1575, 710), (1575, 840), (1600, 840)],
        ),
        (
            "Flow_27_OpToClient",
            "Task_OperatorConsult",
            "Task_ClientReceiveResponse",
            "Ответ специалиста",
            [(1640, 800), (1640, 200)],
        ),
        (
            "Flow_28_OpGate",
            "Task_OperatorConsult",
            "Gateway_NewKnowledge",
            None,
            [(1730, 840), (1770, 840)],
        ),
        (
            "Flow_29_FaqYes",
            "Gateway_NewKnowledge",
            "Task_SubmitFaqDraft",
            "Да",
            [(1795, 815), (1795, 805), (1860, 805)],
        ),
        (
            "Flow_30_FaqNo",
            "Gateway_NewKnowledge",
            "Task_ResolveTicket",
            "Нет",
            [(1795, 865), (1795, 880), (1860, 880)],
        ),
        (
            "Flow_31_FaqClose",
            "Task_SubmitFaqDraft",
            "Task_ResolveTicket",
            None,
            [(1925, 840), (1925, 850)],
        ),
        # Завершение тикета -> Аналитика
        (
            "Flow_32_ToAnalytics",
            "Task_ResolveTicket",
            "Gateway_AnalyticsTrigger",
            None,
            [(1860, 910), (1805, 910), (1805, 975)],
        ),
        (
            "Flow_33_FeedbackToAnalytics",
            "Task_ClientFeedback",
            "Gateway_AnalyticsTrigger",
            "Оценка CSAT",
            [(1840, 200), (1840, 975)],
        ),
        (
            "Flow_34_TriggerAudit",
            "Gateway_AnalyticsTrigger",
            "Task_AuditQuality",
            None,
            [(1830, 1000), (1860, 1000)],
        ),
        (
            "Flow_35_AuditGate",
            "Task_AuditQuality",
            "Gateway_IncidentCheck",
            None,
            [(1990, 1000), (2020, 1000)],
        ),
        (
            "Flow_36_IncYes",
            "Gateway_IncidentCheck",
            "Task_LogIncident",
            "Да",
            [(2045, 975), (2045, 960), (2090, 960)],
        ),
        (
            "Flow_37_IncNo",
            "Gateway_IncidentCheck",
            "End_AuditCompleted",
            "Нет",
            [(2045, 1025), (2045, 1020), (2140, 1020)],
        ),
        (
            "Flow_38_IncEnd",
            "Task_LogIncident",
            "End_AuditCompleted",
            None,
            [(2150, 990), (2158, 990), (2158, 1002)],
        ),
    ]

    incoming_map = defaultdict(list)
    outgoing_map = defaultdict(list)
    for flow_id, src, tgt, _, _ in flows:
        outgoing_map[src].append(flow_id)
        incoming_map[tgt].append(flow_id)

    # Добавляем дорожки
    for lane_id, name, _, _ in lanes_def:
        lane_el = ET.SubElement(
            lane_set, f"{{{NS_BPMN}}}lane", {"id": lane_id, "name": name}
        )
        for node_id in lanes_nodes[lane_id]:
            ref = ET.SubElement(lane_el, f"{{{NS_BPMN}}}flowNodeRef")
            ref.text = node_id

    # Добавляем узлы
    for node_id, n_type, name, _, _ in nodes:
        el = ET.SubElement(
            process, f"{{{NS_BPMN}}}{n_type}", {"id": node_id, "name": name}
        )
        for inc_id in incoming_map[node_id]:
            inc_el = ET.SubElement(el, f"{{{NS_BPMN}}}incoming")
            inc_el.text = inc_id
        for out_id in outgoing_map[node_id]:
            out_el = ET.SubElement(el, f"{{{NS_BPMN}}}outgoing")
            out_el.text = out_id

        if n_type == "endEvent" and "Abuse" in node_id:
            ET.SubElement(el, f"{{{NS_BPMN}}}terminateEventDefinition")

    # Переходы
    for flow_id, src, tgt, name, _ in flows:
        f_attrs = {"id": flow_id, "sourceRef": src, "targetRef": tgt}
        if name:
            f_attrs["name"] = name
        ET.SubElement(process, f"{{{NS_BPMN}}}sequenceFlow", f_attrs)

    # 3. Визуальная диаграмма BPMNDI
    bpmn_diagram = ET.SubElement(
        root, f"{{{NS_BPMNDI}}}BPMNDiagram", {"id": "BPMNDiagram_Support"}
    )
    bpmn_plane = ET.SubElement(
        bpmn_diagram,
        f"{{{NS_BPMNDI}}}BPMNPlane",
        {"id": "BPMNPlane_Support", "bpmnElement": "Collaboration_Support"},
    )

    # Participant Shape
    total_w = 2100
    total_h = 1000
    part_shape = ET.SubElement(
        bpmn_plane,
        f"{{{NS_BPMNDI}}}BPMNShape",
        {
            "id": "Participant_SupportProcess_di",
            "bpmnElement": "Participant_SupportProcess",
            "isHorizontal": "true",
        },
    )
    ET.SubElement(
        part_shape,
        f"{{{NS_DC}}}Bounds",
        {"x": "160", "y": "80", "width": str(total_w), "height": str(total_h)},
    )

    # Lane Shapes
    for lane_id, _, y, h in lanes_def:
        l_shape = ET.SubElement(
            bpmn_plane,
            f"{{{NS_BPMNDI}}}BPMNShape",
            {
                "id": f"{lane_id}_di",
                "bpmnElement": lane_id,
                "isHorizontal": "true",
            },
        )
        ET.SubElement(
            l_shape,
            f"{{{NS_DC}}}Bounds",
            {
                "x": "190",
                "y": str(y),
                "width": str(total_w - 30),
                "height": str(h),
            },
        )

    # Node Shapes
    for node_id, _, _, _, (x, y, w, h) in nodes:
        n_shape = ET.SubElement(
            bpmn_plane,
            f"{{{NS_BPMNDI}}}BPMNShape",
            {"id": f"{node_id}_di", "bpmnElement": node_id},
        )
        ET.SubElement(
            n_shape,
            f"{{{NS_DC}}}Bounds",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h)},
        )

    # Edge Shapes
    for flow_id, _, _, _, waypoints in flows:
        edge = ET.SubElement(
            bpmn_plane,
            f"{{{NS_BPMNDI}}}BPMNEdge",
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        for wx, wy in waypoints:
            ET.SubElement(
                edge, f"{{{NS_DI}}}waypoint", {"x": str(wx), "y": str(wy)}
            )

    xml_bytes = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(xml_bytes)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


if __name__ == "__main__":
    content = create_bpmn()
    with open("docs/support_process.bpmn", "w", encoding="utf-8") as f:
        f.write(content)
    print("Regenerated with standard prefixes!")
