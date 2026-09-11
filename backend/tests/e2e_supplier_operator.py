import asyncio

import httpx


async def test_supplier_to_operator():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Login as supplier
        res_login_s = await client.post(
            "/api/v1/auth/login",
            json={"email": "supplier@example.com", "password": "password123"},
        )
        assert res_login_s.status_code == 200, (
            f"Supplier login failed: {res_login_s.text}"
        )
        s_tokens = res_login_s.json()
        s_token = s_tokens["access_token"]
        s_headers = {"Authorization": f"Bearer {s_token}"}
        print("1. Supplier logged in successfully")

        # Ensure clean state: if supplier has a dangling active ticket from a previous run, resolve it
        res_state = await client.get("/api/v1/chat", headers=s_headers)
        if res_state.status_code == 200:
            active = res_state.json().get("active_ticket")
            if active and active.get("id"):
                print(
                    f"Resolving previous active ticket {active['id']} (status: {active.get('status')})..."
                )
                await client.post(
                    f"/api/v1/chat/tickets/{active['id']}/resolve",
                    headers=s_headers,
                )

        # Send message as supplier
        res_msg = await client.post(
            "/api/v1/chat/messages",
            json={
                "text": "Добрый день! Нужна помощь оператора по процедуре 44-ФЗ."
            },
            headers=s_headers,
        )
        assert res_msg.status_code == 200, (
            f"Supplier send message failed: {res_msg.text}"
        )
        print("2. Supplier message sent successfully")

        # Escalate ticket to operator
        res_esc = await client.post(
            "/api/v1/chat/escalate",
            json={"reason": "Нужна помощь оператора"},
            headers=s_headers,
        )
        assert res_esc.status_code == 200, f"Escalate failed: {res_esc.text}"
        esc_data = res_esc.json()
        print("3. Ticket escalated:", esc_data)
        ticket_id = esc_data["id"]

        # Allow worker / dispatch a moment
        await asyncio.sleep(2)

        # Login as operator
        res_login_o = await client.post(
            "/api/v1/auth/login",
            json={"email": "operator1@example.com", "password": "password123"},
        )
        assert res_login_o.status_code == 200, (
            f"Operator login failed: {res_login_o.text}"
        )
        o_tokens = res_login_o.json()
        o_token = o_tokens["access_token"]
        o_headers = {"Authorization": f"Bearer {o_token}"}
        print("4. Operator logged in successfully")

        # Check operator tickets (poll up to 5s for worker dispatch)
        tickets = []
        for _ in range(5):
            res_tickets = await client.get(
                "/api/v1/operators/tickets", headers=o_headers
            )
            assert res_tickets.status_code == 200, (
                f"Get operator tickets failed: {res_tickets.text}"
            )
            tickets = res_tickets.json()
            if any(t["ticket_id"] == ticket_id for t in tickets):
                break
            await asyncio.sleep(1)
        ticket_ids = [t["ticket_id"] for t in tickets]
        if not any(t["ticket_id"] == ticket_id for t in tickets):
            # Balancer might have selected admin@example.com (who is also active on line L1)
            res_login_admin = await client.post(
                "/api/v1/auth/login",
                json={"email": "admin@example.com", "password": "password123"},
            )
            if res_login_admin.status_code == 200:
                admin_tokens = res_login_admin.json()
                admin_headers = {
                    "Authorization": f"Bearer {admin_tokens['access_token']}"
                }
                res_admin_tickets = await client.get(
                    "/api/v1/operators/tickets", headers=admin_headers
                )
                if res_admin_tickets.status_code == 200:
                    admin_tickets = res_admin_tickets.json()
                    if any(t["ticket_id"] == ticket_id for t in admin_tickets):
                        tickets = admin_tickets
                        o_headers = admin_headers
                        ticket_ids = [t["ticket_id"] for t in tickets]
                        print(
                            "4b. Ticket was assigned to admin (active on L1)"
                        )

        print(f"5. Operator received {len(tickets)} tickets: {ticket_ids}")
        assert any(t["ticket_id"] == ticket_id for t in tickets), (
            f"Ticket {ticket_id} not found in operator tickets!"
        )

        # Open ticket in operator workspace
        res_open = await client.post(
            f"/api/v1/operators/tickets/{ticket_id}/open", headers=o_headers
        )
        assert res_open.status_code == 200, (
            f"Open ticket failed: {res_open.text}"
        )
        ws_data = res_open.json()
        print(
            "6. Operator opened ticket workspace, status:", ws_data["status"]
        )
        assert ws_data["status"] == "in_progress"

        # Operator replies to supplier
        res_reply = await client.post(
            f"/api/v1/operators/tickets/{ticket_id}/messages",
            json={"text": "Здравствуйте! Я оператор Анна, готова вам помочь."},
            headers=o_headers,
        )
        assert res_reply.status_code in (200, 201), (
            f"Operator reply failed: {res_reply.text}"
        )
        print("7. Operator reply sent successfully")

        # Operator completes the ticket
        res_resolve = await client.post(
            f"/api/v1/operators/tickets/{ticket_id}/resolve", headers=o_headers
        )
        assert res_resolve.status_code == 200, (
            f"Operator resolve failed: {res_resolve.text}"
        )
        print("8. Operator resolved ticket successfully")

        print(
            "SUCCESS: Ticket from test supplier is routed to test operator and handled!"
        )


if __name__ == "__main__":
    asyncio.run(test_supplier_to_operator())
