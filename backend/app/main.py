import json

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent import AssistantRequest, AssistantResponse, OpenRouterAgent
from .chat_history import (
    ChatHistoryStore,
    ChatSessionDetail,
    ChatSessionSummary,
    CreateChatSessionRequest,
)


class Product(BaseModel):
    name: str
    value: int
    change: str


class Portfolio(BaseModel):
    customer_count: int
    transaction_volume: int
    risk_score: int
    uptime: str
    products: list[Product]


app = FastAPI(title="PolyFintech 2026 API", version="0.1.0")
agent = OpenRouterAgent()
chat_history = ChatHistoryStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "polyfintech2026"}


@app.get("/api/portfolio", response_model=Portfolio)
def portfolio() -> Portfolio:
    return Portfolio(
        customer_count=12840,
        transaction_volume=4280000,
        risk_score=18,
        uptime="99.98%",
        products=[
            Product(name="Digital Wallets", value=1820000, change="+18.4%"),
            Product(name="SME Lending", value=1410000, change="+11.2%"),
            Product(name="Cross-border Pay", value=1050000, change="+9.7%"),
        ],
    )


@app.get("/api/assistant/sessions", response_model=list[ChatSessionSummary])
def assistant_sessions() -> list[ChatSessionSummary]:
    return chat_history.list_sessions()


@app.post("/api/assistant/sessions", response_model=ChatSessionSummary)
def create_assistant_session(
    request: CreateChatSessionRequest,
) -> ChatSessionSummary:
    return chat_history.create_session(title=request.title)


@app.get("/api/assistant/sessions/{session_id}", response_model=ChatSessionDetail)
def assistant_session(session_id: str) -> ChatSessionDetail:
    try:
        return chat_history.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found.") from exc


@app.delete("/api/assistant/sessions/{session_id}", status_code=204)
def delete_assistant_session(session_id: str) -> Response:
    if not chat_history.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return Response(status_code=204)


@app.post("/api/assistant/chat", response_model=AssistantResponse)
async def assistant_chat(request: AssistantRequest) -> AssistantResponse:
    session = chat_history.ensure_session(request.session_id)
    effective_request = request.model_copy(update={"session_id": session.id})
    persist_latest_user_message(session.id, request)
    response = await agent.run(effective_request)
    chat_history.append_assistant_response(
        session.id,
        response,
        request.page_context,
    )
    return response


@app.post("/api/assistant/chat/stream")
async def assistant_chat_stream(request: AssistantRequest) -> StreamingResponse:
    session = chat_history.ensure_session(request.session_id)
    effective_request = request.model_copy(update={"session_id": session.id})
    persist_latest_user_message(session.id, request)

    async def events():
        async for event in agent.stream(effective_request):
            if event.get("type") == "final" and event.get("response"):
                response = AssistantResponse(**event["response"])
                chat_history.append_assistant_response(
                    session.id,
                    response,
                    request.page_context,
                )
                event["session"] = chat_history.get_session_summary(
                    session.id,
                ).model_dump(by_alias=True)
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


def persist_latest_user_message(session_id: str, request: AssistantRequest) -> None:
    for message in reversed(request.messages):
        if message.role == "user":
            chat_history.append_user_message(
                session_id,
                message.content,
                request.page_context,
            )
            return
