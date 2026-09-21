# `mcpDonotKnow.pdf` 학습 정리

이 문서는 `mcpDonotKnow.pdf`에 정리된 MCP 관련 낯선 개념을 이 프로젝트의 코드와 연결해 다시 설명한 학습 노트다.

## 1. MCP를 먼저 한 문장으로 이해하기

**MCP(Model Context Protocol)는 AI 프로그램이 외부 기능을 발견하고 호출하기 위한 공통 통신 규칙이다.**

MCP는 특정 서버 제품이나 Python 라이브러리의 이름이 아니다. 다음 대화를 일정한 형식으로 주고받기 위한 약속이다.

```text
Client: 사용할 수 있는 기능을 알려 주세요.  → tools/list
Server: Tool 이름·설명·입력 Schema를 보냅니다.
Client: 이 Tool을 이 인자로 실행해 주세요.   → tools/call
Server: 실행 결과를 보냅니다.
```

## 2. MCP Host, Client, Server 구분

용어가 비슷해서 가장 많이 헷갈리는 부분이다.

| 개념 | 쉬운 설명 | 이 프로젝트에서 |
| --- | --- | --- |
| MCP Host | MCP를 사용하는 전체 애플리케이션 | FastAPI Backend + Agent 구조 |
| MCP Client | Server와 연결하고 메시지를 주고받는 연결 담당자 | `backend/app/mcp_client.py` |
| MCP Server | Tool과 Resource를 제공하고 실제 기능을 실행하는 프로그램 | `mcp_server/` 안의 두 Python 파일 |
| Tool | 인자를 받아 작업을 수행하는 호출 가능한 기능 | 날씨 조회, 호텔 검색, 정책 조회 |
| Resource | URI로 읽는 정보·문서 | `travel://policy/baggage` |
| Transport | MCP 메시지가 이동하는 통로 | Streamable HTTP, stdio |

비유하면 다음과 같다.

```text
Host    = 식당 전체 시스템
Client  = 주문을 전달하는 직원
Server  = 실제 요리를 하는 주방
Tool    = 주문 가능한 메뉴
Resource= 이미 준비되어 있어 읽어 오는 안내문
```

## 3. Tool은 왜 필요한가?

LLM은 질문을 이해하고 답변을 작성할 수 있지만, 프로그램 바깥의 데이터를 직접 조회하지는 못한다. Tool을 연결하면 LLM은 다음과 같이 행동을 제안할 수 있다.

```json
{
  "name": "travel__search_hotels",
  "arguments": {
    "city": "부산",
    "max_price": 150000
  }
}
```

여기서 중요한 점은 **이 JSON을 보고 실제 함수를 실행하는 주체가 LLM이 아니라 Backend**라는 것이다.

```text
LLM: 어떤 Tool과 인자가 필요한지 결정
Backend: MCP Client로 Server에 call_tool 요청
Server: 실제 Python 함수 실행
Backend: 결과를 LLM에 전달
LLM: 다음 Tool 또는 최종 답변 결정
```

## 4. Tool Schema란?

Tool Schema는 Tool 사용 설명서다.

```text
이름: search_hotels
설명: 도시와 최대 가격으로 호텔을 검색한다.
입력:
  city: 문자열
  max_price: 정수, 기본값 150000
```

Schema가 있어야 LLM이 인자 이름과 타입을 알 수 있다. 이 프로젝트에서는 MCP Server가 Schema를 공개하고, Backend가 발견한 Schema를 OpenAI Tool 형식으로 변환한다.

```text
@mcp.tool() 함수
    ↓ MCP Server가 Schema로 공개
session.list_tools()
    ↓
to_openai_tool()
    ↓
OpenAI Responses API의 tools 배열
```

## 5. `tools/list`와 `tools/call`

### `tools/list`

Server가 제공하는 기능 목록을 조회한다.

```text
Client → Server: tools/list
Server → Client:
  - get_current_weather
  - search_hotels
  - get_hotel_policy
```

이 프로젝트에서는 `mcp_client.py`의 다음 코드들이 이 의미를 담당한다.

```python
response = await session.list_tools()
```

### `tools/call`

특정 Tool을 인자와 함께 실행한다.

```python
result = await sessions[route["server"]].call_tool(
    route["tool"],
    arguments,
)
```

`route["server"]`는 어느 Server로 보낼지, `route["tool"]`은 그 Server 안의 실제 Tool 이름을 뜻한다.

## 6. MCP Server 두 종류

### Streamable HTTP Server

`travel_server.py`는 `8010/mcp`에서 독립 실행된다.

```text
Backend :8000 ── HTTP ──> Travel MCP Server :8010
```

장점은 Backend와 별도의 프로세스·포트에서 실행되므로 다른 Client나 서비스도 연결할 수 있다는 점이다.

### stdio Server

`policy_stdio_server.py`는 Backend가 자식 프로세스로 실행한다.

```text
Backend ── stdin/stdout ──> Policy MCP Server 프로세스
```

포트가 필요 없고 로컬 프로세스를 직접 연결한다. 기능은 HTTP Server와 다르지 않으며, 달라지는 것은 Transport와 프로세스 수명이다.

## 7. MCP Client의 수명

Client는 단순한 함수 하나가 아니라 연결 Session을 관리한다.

```text
Transport 열기
  → ClientSession 만들기
  → session.initialize()
  → tools/list 또는 tools/call
  → 작업 종료
  → Session과 자식 프로세스 정리
```

`AsyncExitStack`은 여러 Session을 열어 둔 뒤 함수가 끝날 때 안전하게 닫도록 돕는다. 따라서 `mcp_sessions()` 안에서 Travel과 Policy Session을 함께 관리할 수 있다.

## 8. Resource는 Tool과 다르다

Tool은 작업을 시킨다.

```text
호텔을 검색해 주세요.
→ search_hotels(city="부산", max_price=150000)
```

Resource는 정해진 내용을 읽는다.

```text
수하물 정책을 읽어 주세요.
→ read_resource("travel://policy/baggage")
```

이 프로젝트의 `baggage_policy()`는 값을 계산하는 Tool이 아니라 읽을 수 있는 문서를 제공하므로 `@mcp.resource()`가 붙는다.

## 9. Agent Loop란?

Agent Loop는 “판단 → 실행 → 결과 확인 → 다시 판단”의 반복이다.

```text
질문 입력
  ↓
LLM이 Tool 선택
  ↓
Backend가 MCP Tool 실행
  ↓
결과를 LLM에 전달
  ↓
더 필요한 Tool이 있는가?
  ├─ 예: 다시 Tool 선택
  └─ 아니오: 최종 답변
```

`agent.py`에서는 `MAX_AGENT_ROUNDS = 8`까지 반복하고, `parallel_tool_calls=False`로 한 Round에 Tool 하나만 실행하도록 한다.

## 10. 이 프로젝트를 통해 기억할 핵심 문장

1. MCP는 AI와 외부 기능을 연결하는 표준 통신 규칙이다.
2. MCP Server는 기능을 제공하고, MCP Client는 그 기능을 발견·호출한다.
3. Tool은 작업을 수행하고, Resource는 내용을 읽는다.
4. GPT는 Tool을 선택하지만, Tool을 직접 실행하지 않는다.
5. Backend가 MCP Client이자 실행 통제 지점이다.
6. HTTP와 stdio는 MCP의 종류가 아니라 메시지를 운반하는 Transport의 차이다.
7. 이전 Tool의 결과가 다음 Tool의 입력이 되면 Tool chaining이다.

