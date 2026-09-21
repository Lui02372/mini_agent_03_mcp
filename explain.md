# Mini Agent 03 · MCP 발표용 설명서

> 대상: `mini_agent_03_mcp`를 처음 보는 사람
>
> 발표 목표: Tool, MCP, MCP Client, MCP Server가 왜 필요한지 설명하고, 사용자의 질문이 최종 답변이 되기까지의 흐름을 코드와 연결해 말할 수 있다.

---

## 0. 발표 시작: 이 프로젝트를 한 문장으로 말하면

**이 프로젝트는 여행 기능을 Backend 안에 직접 넣지 않고 MCP Server로 분리한 뒤, FastAPI Backend가 MCP Client가 되어 필요한 Tool을 발견하고 호출하는 Agent 애플리케이션이다.**

발표에서는 다음 질문에 답하면 된다.

1. Tool은 무엇인가?
2. MCP는 왜 필요한가?
3. Client와 Server는 누가 맡는가?
4. 사용자의 질문은 실제로 어떤 순서로 처리되는가?

전체 구조는 다음과 같다.

```text
사용자
  ↓
Streamlit Frontend :8501
  ↓ HTTP
FastAPI Backend :8000
  ├─ MCP Client ── Streamable HTTP ── Travel MCP Server :8010
  └─ MCP Client ── stdio ─────────── Policy MCP Server(자식 프로세스)
  ↓
OpenAI Responses API: 어떤 Tool을 쓸지 결정
```

중요한 경계는 이것이다.

> GPT는 Tool을 **선택**하고, Backend는 MCP를 통해 Tool을 **실행**한다.
> MCP Server가 제공하는 실제 기능은 GPT나 Frontend가 직접 실행하지 않는다.

---

## 1. Tool이란 무엇인가?

### 발표용 정의

**Tool은 프로그램이 외부 세계에서 일을 하도록 만든 호출 가능한 기능이다.**

LLM은 글을 잘 만들지만, 스스로 부산 날씨를 조회하거나 호텔 데이터베이스를 검색하지는 못한다. 그래서 프로그램 함수에 이름, 설명, 입력 형식을 붙여 LLM이 선택할 수 있게 만든다.

예를 들어 이 프로젝트에는 다음 Tool이 있다.

| 공개 이름 | 실제 기능 | 입력 예시 |
| --- | --- | --- |
| `travel__get_current_weather` | 도시의 날씨 조회 | `{"city": "부산"}` |
| `travel__search_hotels` | 도시와 가격으로 호텔 검색 | `{"city": "부산", "max_price": 150000}` |
| `policy__get_hotel_policy` | 호텔 ID로 정책 조회 | `{"hotel_id": "hotel-busan-001"}` |

### Tool에는 왜 Schema가 필요한가?

LLM에게 함수 코드 전체를 보여주는 것이 아니라, 다음 계약만 전달한다.

```text
이 Tool의 이름은 무엇인가?
무슨 일을 하는가?
어떤 인자를 어떤 타입으로 받아야 하는가?
```

이 계약이 Schema다. `travel_server.py`의 `Literal`과 기본값은 MCP가 Tool 입력 Schema로 노출한다. `mcp_client.py`는 이 Schema를 `tools/list`로 받아오고, `agent.py`는 OpenAI Tool 형식으로 변환한다.

### Tool 호출의 핵심

Tool 호출은 보통 다음 3단계다.

```text
1. Tool 발견: tools/list
2. Tool 선택: LLM이 function_call 생성
3. Tool 실행: tools/call + arguments
```

Tool 결과는 다시 LLM에게 전달된다. LLM은 그 결과를 보고 다음 Tool을 부를지, 최종 답변을 만들지 결정한다.

---

## 2. MCP란 무엇인가?

### 발표용 정의

**MCP(Model Context Protocol)는 AI 애플리케이션이 외부 기능과 표준 방식으로 연결되도록 정한 통신 규칙이다.**

MCP의 핵심은 특정 Python 함수나 특정 회사의 API가 아니다. 서로 다른 프로그램 사이에서 다음과 같은 약속을 지키는 것이다.

```text
Client: 어떤 Tool이 있나요?       → tools/list
Server: 이런 Tool들이 있습니다.   ← 이름·설명·입력 Schema
Client: 이 Tool을 이 인자로 실행해 주세요. → tools/call
Server: 실행 결과입니다.           ← content / isError
```

### MCP가 없을 때와 있을 때

| 직접 연결 방식 | MCP 방식 |
| --- | --- |
| Backend가 여행 함수 모듈을 직접 import | Backend가 MCP Client만 사용 |
| Tool 목록과 호출 규칙이 Backend에 고정 | Server가 `tools/list`로 자기 기능을 공개 |
| Python 함수 호출에 강하게 결합 | `tools/call`이라는 공통 프로토콜 사용 |
| 기능을 다른 앱에서 재사용하기 어려움 | 여러 Client가 같은 Server를 재사용 가능 |

MCP는 “LLM이 알아서 코드를 실행하는 마법”이 아니다. **기능을 제공하는 Server와 그 기능을 사용하는 Client 사이의 표준 계약**이다.

---

## 3. MCP Server는 무엇을 하는가?

### 발표용 정의

**MCP Server는 Tool, Resource 같은 기능을 공개하고, Client의 요청을 받아 실제 코드를 실행하는 프로그램이다.**

이 프로젝트에서는 Server가 두 개다.

### 3-1. Travel MCP Server: Streamable HTTP

`mcp_server/travel_server.py`는 `FastMCP`로 서버를 만들고 `@mcp.tool()`로 날씨·호텔 검색 기능을 공개한다. `@mcp.resource()`로 수하물 정책 Resource도 공개한다.

- 독립 프로세스로 실행된다.
- `127.0.0.1:8010/mcp`에서 대기한다.
- Backend는 네트워크를 통해 접속한다.
- 서버가 내려가면 Backend의 MCP 상태 확인이 실패한다.

### 3-2. Policy MCP Server: stdio

`mcp_server/policy_stdio_server.py`는 호텔 정책 Tool을 제공한다.

- 별도 포트가 없다.
- Backend가 `sys.executable`과 Python 파일 경로로 자식 프로세스를 실행한다.
- 표준 입력(stdin)과 표준 출력(stdout)으로 MCP 메시지를 주고받는다.
- stdout은 MCP 메시지 전용이므로 일반 로그를 섞으면 안 된다.

### Transport는 무엇인가?

**Transport는 MCP 메시지가 이동하는 통로**다. MCP의 Tool 의미는 같고 통로만 다르다.

```text
Streamable HTTP: Backend ── HTTP ──> Travel Server :8010
stdio:           Backend ── stdin/stdout ──> Policy Server 프로세스
```

발표에서 “HTTP와 stdio는 서로 다른 MCP인가요?”라고 질문받으면 이렇게 답한다.

> 아닙니다. 둘 다 같은 MCP 규칙을 사용하고, 메시지를 운반하는 Transport만 다릅니다.

---

## 4. MCP Client는 무엇을 하는가?

### 발표용 정의

**MCP Client는 MCP Server에 연결해 세션을 만들고, 기능을 발견하고, 요청을 전달하고, 결과를 받는 쪽이다.**

이 프로젝트에서는 FastAPI Backend 안의 `backend/app/mcp_client.py`가 Client 역할을 한다.

### Client의 책임

1. 설정에 맞는 Transport 열기
2. `ClientSession` 만들기
3. `session.initialize()`로 MCP 세션 초기화
4. `session.list_tools()`로 Tool 목록 받기
5. `session.call_tool(name, arguments)`로 실행 요청
6. `session.list_resources()`와 `read_resource()`로 Resource 사용
7. `AsyncExitStack`으로 연결과 자식 프로세스 정리

`MCP_SERVERS` 설정에는 Server 이름과 연결 방법이 들어 있다.

```python
"travel": {"transport": "streamable-http", "url": "http://127.0.0.1:8010/mcp"}
"policy": {"transport": "stdio", "command": sys.executable, "args": [...]}
```

이 설정 때문에 Client는 두 Server를 같은 방식으로 다루면서도 연결 방법은 각각 다르게 선택할 수 있다.

---

## 5. Tool과 Resource의 차이

둘 다 MCP Server가 공개하지만 목적이 다르다.

| 구분 | Tool | Resource |
| --- | --- | --- |
| 목적 | 어떤 작업을 수행 | 내용을 읽어오기 |
| 호출 | `tools/call` | URI 기반 `read_resource` |
| 입력 | 인자 Schema | `travel://policy/baggage` 같은 URI |
| 예시 | 호텔 검색, 정책 조회 | 수하물 정책 문서 |
| 이 프로젝트의 경로 | `/api/mcp/run`에서 Agent가 선택 | `/api/mcp/baggage-policy`에서 Backend가 읽음 |

수하물 정책은 계산·검색 작업을 시키는 Tool이 아니라, 정해진 문서를 읽는 Resource다. 따라서 `baggage_policy()`에는 `@mcp.resource("travel://policy/baggage")`가 붙어 있다.

---

## 6. 실제 질문 한 개를 따라가기

질문:

> “부산 날씨와 15만원 이하 호텔을 찾고, 검색된 호텔의 정책도 알려 주세요.”

### 단계 1: Frontend → Backend

Streamlit의 `post("/api/mcp/run", {"question": question})`가 FastAPI의 `POST /api/mcp/run`을 호출한다. Frontend는 MCP Server를 직접 알지 못한다.

### 단계 2: Backend가 MCP Session 연결

`run_agent()`가 `mcp_sessions()`를 열어 travel HTTP Session과 policy stdio Session을 만든다. 각 Session은 초기화된다.

### 단계 3: Backend가 Tool 목록 수집

각 Session에서 `list_tools()`를 실행한다. Server 이름을 붙여 공개 이름과 라우팅 정보를 만든다.

```text
travel + get_current_weather → travel__get_current_weather
travel + search_hotels       → travel__search_hotels
policy + get_hotel_policy    → policy__get_hotel_policy
```

이름을 합치는 이유는 서로 다른 Server에 같은 Tool 이름이 있어도 구분하기 위해서다.

### 단계 4: GPT가 다음 행동 선택

Backend는 Tool Schema를 OpenAI Responses API의 `tools`로 전달한다. GPT는 질문을 보고 한 번에 Tool 하나를 선택한다. `parallel_tool_calls=False` 설정으로 이 학습 프로젝트는 순차 실행을 강제한다.

### 단계 5: 첫 번째 Tool 실행

GPT가 `travel__get_current_weather`를 선택했다면 Backend는 공개 이름을 라우팅 테이블에서 찾는다.

```text
travel__get_current_weather
  → server = travel
  → tool   = get_current_weather
  → travel Session의 call_tool 실행
```

GPT가 Tool을 실행하는 것이 아니라 Backend가 `sessions["travel"].call_tool(...)`을 실행한다.

### 단계 6: 결과를 GPT에게 되돌려주기

Backend는 결과를 `function_call_output`으로 포장하고 `previous_response_id`와 함께 다시 Responses API에 전달한다. 그러면 GPT는 방금 결과를 문맥으로 볼 수 있다.

### 단계 7: 의존하는 다음 Tool 실행

호텔 정책을 알려면 먼저 호텔 검색 결과의 `hotel_id`가 필요하다.

```text
search_hotels 결과
  → hotel_id = hotel-busan-001
  → get_hotel_policy(hotel_id="hotel-busan-001")
```

이것은 **Tool chaining** 또는 **순차 Tool 호출**이다. 앞 Tool의 출력이 뒤 Tool의 입력이 된다.

### 단계 8: 최종 답변과 종료

GPT가 더 이상 `function_call`을 내놓지 않고 답변 텍스트를 만들면 Loop가 끝난다. 반환값에는 최종 `answer`뿐 아니라 `trace`, `llm_calls`, `available_tools`도 들어간다.

일반적으로 Tool을 3번 실행하면 LLM 호출은 “Tool을 고르는 호출 3번 + 최종 답변 호출 1번”으로 4번이 된다.

---

## 7. 코드 파일별 발표 포인트

| 파일 | 발표할 역할 |
| --- | --- |
| `frontend/app.py` | 사용자 화면. Backend API만 호출 |
| `backend/app/main.py` | FastAPI 엔드포인트와 예외를 HTTP 응답으로 변환 |
| `backend/app/mcp_client.py` | HTTP·stdio 연결, Session, Tool/Resource 발견과 호출 |
| `backend/app/agent.py` | GPT Tool Schema 변환, 라우팅, 반복 실행, Trace |
| `backend/app/schemas.py` | 요청·응답·실행 Trace의 데이터 모양 |
| `mcp_server/travel_server.py` | 여행 Tool 2개와 Resource 1개 제공 |
| `mcp_server/policy_stdio_server.py` | 호텔 정책 Tool 제공 |

### 발표자가 꼭 짚을 함수

- `open_session()`: Transport별 연결을 열고 `ClientSession`을 초기화한다.
- `mcp_sessions()`: 등록된 모든 Server Session을 한 번에 관리한다.
- `discover_tools()`: `tools/list` 결과를 공개용 목록으로 바꾼다.
- `to_openai_tool()`: MCP Tool Schema를 OpenAI function Tool Schema로 바꾼다.
- `run_agent()`: LLM 호출 → Tool 라우팅 → MCP 실행 → 결과 전달을 반복한다.
- `main.py`의 `run_mcp_agent()`: HTTP 요청을 Agent 실행으로 연결한다.

---

## 8. 자주 헷갈리는 개념 정리

### “MCP Server가 LLM인가요?”

아니다. MCP Server는 날씨 조회, 호텔 검색, 정책 조회처럼 정해진 프로그램 기능을 제공한다. 어떤 기능을 쓸지는 LLM 또는 애플리케이션이 결정한다.

### “MCP Client가 Frontend인가요?”

이 프로젝트에서는 아니다. Frontend는 FastAPI Backend를 호출하고, Backend 내부의 `mcp_client.py`가 MCP Client다.

### “Tool Schema만 보내면 Tool이 실행되나요?”

아니다. Schema는 선택을 위한 설명서다. 실제 실행은 Backend가 올바른 Server Session에 `call_tool()`을 보내야 한다.

### “HTTP Server와 stdio Server의 기능이 다른가요?”

기능보다 Transport 차이가 핵심이다. HTTP는 네트워크 주소로 연결하고, stdio는 자식 프로세스의 표준 입출력으로 연결한다.

### “Resource도 Tool인가요?”

아니다. Resource는 URI로 식별되는 읽기 대상이고, Tool은 인자를 받아 작업을 수행하는 호출 기능이다.

### “MCP가 있으면 보안이 자동으로 해결되나요?”

아니다. 이 프로젝트처럼 Frontend가 Backend만 호출하게 하고, Backend가 허용된 Server와 Tool을 관리하는 구조가 보안 경계를 만드는 데 도움을 준다. 실제 서비스에서는 인증, 인가, 입력 검증, 로그, 위험 작업 승인도 별도로 필요하다.

---

## 9. 발표 마무리: 30초 요약

> Tool은 AI가 사용할 수 있는 호출 가능한 프로그램 기능입니다. MCP는 그런 기능을 Client와 Server 사이에서 표준 방식으로 발견하고 실행하기 위한 프로토콜입니다. MCP Server는 Tool과 Resource를 공개하고, MCP Client는 Session을 통해 목록 조회와 실행 요청을 담당합니다. 이 프로젝트에서는 FastAPI Backend가 MCP Client이고, Travel Server는 Streamable HTTP, Policy Server는 stdio로 연결됩니다. GPT는 Tool을 선택할 뿐 직접 실행하지 않으며, Backend가 라우팅 테이블로 올바른 Server에 호출하고 결과를 다시 GPT에게 전달합니다. 그래서 호텔 검색 결과의 `hotel_id`를 정책 조회 Tool에 넘기는 순차 Agent Loop가 완성됩니다.

---

## 10. 발표 시연 체크리스트

- [ ] Travel MCP Server가 `8010/mcp`에서 실행 중인가?
- [ ] Backend의 `/api/mcp/status`가 `connected`인가?
- [ ] `/api/mcp/tools`에서 3개 Tool과 Schema가 보이는가?
- [ ] `travel__`, `policy__` prefix가 붙었는가?
- [ ] 호텔 검색 결과의 `hotel_id`가 Policy Tool 입력으로 이어지는가?
- [ ] `/api/mcp/baggage-policy`가 Resource 조회임을 설명했는가?
- [ ] Trace에서 GPT 선택과 Backend 실행을 구분해 말했는가?
