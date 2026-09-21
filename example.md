# Backend · Frontend 함수 이해 예제

## 예제 질문

다음 질문을 실제 코드가 어떻게 처리하는지 따라간다.

> **“부산에서 15만원 이하 호텔을 찾아 주세요.”**

이 예제의 목표는 최종 답변 자체보다, Frontend의 함수가 Backend의 함수로 어떻게 이어지고, Backend가 MCP Server의 Tool을 어떻게 실행하는지 이해하는 것이다.

---

## 1. 먼저 실행 중인 구성

```text
브라우저
  ↓
frontend/app.py
  ↓ httpx.post()
FastAPI backend/app/main.py
  ↓
backend/app/agent.py
  ↓ MCP Client
mcp_server/travel_server.py
```

`frontend/app.py`는 MCP Server에 직접 연결하지 않는다. Frontend는 Backend 주소만 알고, MCP 연결과 Tool 실행은 Backend가 담당한다.

---

## 2. Frontend에서 시작: `post()`

사용자가 **MCP Agent 실행** 버튼을 누르면 다음 코드 흐름이 시작된다.

```python
if st.button("MCP Agent 실행", type="primary"):
    result = post("/api/mcp/run", {"question": question})
```

### `post()` 함수

```python
def post(path: str, payload: dict) -> dict:
    response = httpx.post(
        f"{BASE_URL}{path}",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()
```

한 줄씩 해석하면 다음과 같다.

| 코드 | 의미 |
| --- | --- |
| `BASE_URL` | 기본값은 `http://127.0.0.1:8000` |
| `f"{BASE_URL}{path}"` | 실제 주소를 `/api/mcp/run`으로 조합 |
| `json=payload` | 질문을 JSON Body로 전송 |
| `raise_for_status()` | 400·503 오류면 예외 발생 |
| `response.json()` | Backend JSON 응답을 Python dict로 변환 |

전송되는 HTTP 요청은 개념적으로 다음과 같다.

```http
POST http://127.0.0.1:8000/api/mcp/run
Content-Type: application/json

{"question": "부산에서 15만원 이하 호텔을 찾아 주세요."}
```

---

## 3. Backend 입구: `run_mcp_agent()`

`backend/app/main.py`에서 요청을 받는다.

```python
@app.post("/api/mcp/run", response_model=McpRunResult)
async def run_mcp_agent(payload: McpRunRequest) -> McpRunResult:
    try:
        return await run_agent(payload.question)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error))
```

### 이 함수의 역할

1. URL과 HTTP Method로 요청을 받는다.
2. `McpRunRequest`로 질문 형식을 검증한다.
3. 실제 Agent 작업은 `run_agent()`에 위임한다.
4. 성공하면 `McpRunResult`를 JSON으로 반환한다.
5. 사용자의 잘못된 입력은 400, 연결·서버 문제는 503으로 바꾼다.

즉 `main.py`의 함수는 여행 Tool을 직접 실행하지 않는다. **HTTP 문과와 오류 변환을 담당한다.**

---

## 4. Agent 시작: `run_agent(question)`

`backend/app/agent.py`의 `run_agent()`가 판단과 실행을 연결한다.

### 4-1. MCP Session 열기

```python
async with AsyncOpenAI() as client, mcp_sessions() as sessions:
```

이 줄에서 두 종류의 연결이 준비된다.

```text
client   = OpenAI Responses API 연결
sessions = {
  "travel": Travel HTTP MCP Session,
  "policy": Policy stdio MCP Session
}
```

`mcp_sessions()`는 `mcp_client.py`의 `open_session()`을 사용한다.

```text
mcp_sessions()
  ├─ open_session(travel)
  │    └─ streamable_http_client("http://127.0.0.1:8010/mcp")
  └─ open_session(policy)
       └─ stdio_client(policy_stdio_server.py)
```

### 4-2. Tool 목록 발견

```python
for server_name, session in sessions.items():
    discovered = (await session.list_tools()).tools
```

여기서 Backend는 Tool을 직접 import하지 않고 Server에게 “무슨 기능이 있나요?”라고 묻는다.

결과는 대략 다음처럼 구성된다.

```text
travel__get_current_weather
travel__search_hotels
policy__get_hotel_policy
```

### 4-3. OpenAI 형식과 MCP 라우팅 만들기

```python
openai_tool, route = to_openai_tool(server_name, tool)
openai_tools.append(openai_tool)
routes[openai_tool["name"]] = route
```

예를 들어 `search_hotels`는 다음 두 가지 정보로 분리된다.

```python
openai_tool = {
    "type": "function",
    "name": "travel__search_hotels",
    "parameters": {"...": "input schema"}
}

route = {
    "server": "travel",
    "tool": "search_hotels"
}
```

앞의 `openai_tool`은 GPT에게 보여주는 설명서이고, 뒤의 `route`는 Backend가 실제 목적지를 찾기 위한 지도다.

---

## 5. GPT가 Tool을 선택하는 순간

```python
response = await client.responses.create(
    model=OPENAI_MODEL,
    instructions=INSTRUCTIONS,
    input=input_items,
    tools=openai_tools,
    parallel_tool_calls=False,
)
```

GPT는 질문과 Tool Schema를 보고 다음과 같은 `function_call`을 반환할 수 있다.

```json
{
  "type": "function_call",
  "name": "travel__search_hotels",
  "arguments": "{\"city\":\"부산\",\"max_price\":150000}"
}
```

이 시점에는 아직 호텔 함수가 실행되지 않았다. GPT가 “이 Tool을 이 인자로 써야겠다”고 제안만 한 상태다.

---

## 6. Backend가 MCP Tool을 실행하는 순간

먼저 공개 이름으로 라우팅 정보를 찾는다.

```python
call = tool_calls[0]
route = routes.get(call.name)
arguments = json.loads(call.arguments)
```

값은 다음과 같아진다.

```text
call.name       = travel__search_hotels
route[server]   = travel
route[tool]     = search_hotels
arguments       = {"city": "부산", "max_price": 150000}
```

그 다음 실제 MCP 호출을 보낸다.

```python
result = await sessions[route["server"]].call_tool(
    route["tool"],
    arguments,
)
```

실제 이동은 다음과 같다.

```text
sessions["travel"]
  → Travel MCP Session
  → tools/call
  → search_hotels(city="부산", max_price=150000)
  → travel_server.py의 Python 함수
```

Server는 다음과 비슷한 결과를 돌려준다.

```json
{
  "items": [
    {
      "hotel_id": "hotel-busan-001",
      "name": "바다 호텔",
      "city": "부산",
      "price": 120000
    }
  ],
  "source": "travel-hotel-catalog"
}
```

---

## 7. 결과를 GPT에게 다시 전달

Backend는 결과를 Trace에 기록한 뒤 GPT가 읽을 수 있는 형태로 포장한다.

```python
tool_output = {
    "server": route["server"],
    "tool": route["tool"],
    "success": not bool(result.isError),
    "content": output,
}

input_items = [{
    "type": "function_call_output",
    "call_id": call.call_id,
    "output": json.dumps(tool_output, ensure_ascii=False),
}]
```

그리고 다음 반복에서 이 결과를 입력으로 사용한다.

```text
호텔 검색 결과
  → GPT에게 전달
  → GPT가 “이제 정책 Tool이 필요하다”고 판단
```

이번 질문은 호텔 정보만 요청했으므로 GPT는 최종 답변을 만들고 Loop가 끝난다.

---

## 8. Backend 응답이 Frontend 화면으로 돌아오기

`run_agent()`가 반환한 `McpRunResult`는 다음 정보를 포함한다.

```json
{
  "question": "부산에서 15만원 이하 호텔을 찾아 주세요.",
  "model": "gpt-4.1-mini",
  "available_tools": ["policy__get_hotel_policy", "travel__search_hotels"],
  "llm_calls": 2,
  "trace": ["..."],
  "answer": "부산의 15만원 이하 호텔은 바다 호텔입니다."
}
```

Frontend는 응답을 받은 뒤 다음 코드로 화면에 표시한다.

```python
result = post("/api/mcp/run", {"question": question})
st.success(result["answer"])
left.metric("GPT 호출 횟수", result["llm_calls"])
right.metric("실행된 Tool 수", len(result["trace"]))
```

Trace는 반복문으로 표시한다.

```python
for item in result["trace"]:
    st.caption(f"Public Tool: {item['public_tool']}")
    st.json(item["arguments"])
    st.code(item["result"])
```

그래서 화면에서 다음을 확인할 수 있다.

```text
GPT가 선택한 공개 Tool 이름
→ 전달된 arguments
→ MCP Server가 돌려준 결과
→ 최종 answer
```

---

## 9. 함수 호출 전체를 한 줄로 연결하기

```text
사용자 클릭
  → frontend/app.py의 st.button()
  → frontend/app.py의 post()
  → backend/app/main.py의 run_mcp_agent()
  → backend/app/agent.py의 run_agent()
  → agent.py의 mcp_sessions()
  → mcp_client.py의 open_session()
  → agent.py의 session.list_tools()
  → OpenAI responses.create()
  → routes 조회
  → session.call_tool()
  → travel_server.py의 search_hotels()
  → function_call_output
  → 최종 McpRunResult
  → Frontend의 st.success(), metric(), trace 화면
```

## 10. 이 예제에서 꼭 기억할 것

- Frontend 함수는 질문을 Backend로 전달하고 결과를 화면에 그린다.
- `main.py` 함수는 HTTP 요청을 받고 오류 형식을 정리한다.
- `agent.py` 함수는 LLM의 선택과 MCP 실행을 연결한다.
- `mcp_client.py` 함수는 Transport와 Session을 관리한다.
- MCP Server 함수는 최종적으로 실제 데이터를 만든다.
- `call.name`은 GPT가 선택한 공개 이름이고, `route`는 실제 Server와 Tool을 찾는 지도다.
- GPT 호출과 Tool 실행은 별개의 단계다.

---

## 11. 심화: `to_openai_tool()` 한 줄씩 해부하기

함수 이름은 정확히 `to_openai_tool`이다. 뜻은 “MCP Tool 객체를 OpenAI가 이해하는 Tool dict로 바꾼다”이다.

```python
def to_openai_tool(
    server_name: str,
    tool,
) -> tuple[dict[str, Any], dict[str, str]]:
```

### `server_name: str`

`server_name`은 함수에 전달되는 매개변수 이름이고, `str`은 문자열 타입 힌트다.

```python
server_name = "travel"
```

콜론 `:`은 “이 매개변수의 타입 정보를 뒤에 적겠다”는 표시다. 타입 힌트는 설명서에 가깝다. Python이 실행 중 모든 타입을 자동으로 차단하는 장치는 아니다.

### `tool`에 타입 힌트가 없는 이유

`tool`은 `session.list_tools()`가 반환한 MCP SDK 객체다. 현재 코드는 SDK의 구체적인 Tool 모델 타입을 import하지 않고, 실행 시 필요한 속성인 `name`, `description`, `model_dump()`를 사용하는 구조라 타입을 생략했다.

따라서 다음은 서로 다른 의미다.

```python
tool              # 타입 힌트를 생략한 매개변수
tool: SomeType    # 타입을 명시한 매개변수
```

IDE에서 `tool`이 주황색으로 보이는 것은 Python의 특별한 상태가 아니다. 편집기 테마가 매개변수·변수·함수 등을 구분해 칠한 문법 색상이다. 테마를 바꾸면 색도 달라진다.

### `-> tuple[...]`

`->`는 함수의 반환 타입 힌트다.

```python
-> tuple[dict[str, Any], dict[str, str]]
```

이것은 다음 문장으로 읽는다.

> “이 함수는 tuple 하나를 반환한다. tuple의 첫 번째 값은 `dict[str, Any]`, 두 번째 값은 `dict[str, str]`이다.”

이 함수 안에서 변수가 4개 만들어져도 반환값은 `return` 뒤에 적힌 두 개뿐이다.

```python
public_name = ...  # 중간 계산값
raw = ...          # 중간 계산값
openai_tool = ...  # 반환할 첫 번째 값
route = ...        # 반환할 두 번째 값
return openai_tool, route
```

호출하는 쪽에서는 이렇게 받는다.

```python
openai_tool, route = to_openai_tool(server_name, tool)
```

이것을 tuple unpacking이라고 한다. `(값1, 값2)`를 순서대로 왼쪽 변수에 나누어 담는 방식이다.

### `public_name`과 `__`

```python
public_name = f"{server_name}__{tool.name}"
```

예를 들어 다음과 같이 된다.

```text
server_name = "travel"
tool.name   = "search_hotels"
public_name = "travel__search_hotels"
```

`__`는 여기서 Python의 특별 문법이 아니다. 이 프로젝트가 만든 이름 구분자다. Server 이름과 Tool 이름을 합쳐도 나중에 다시 구분할 수 있게 Namespace처럼 사용한다.

### `raw`의 역할

```python
raw = tool.model_dump(by_alias=True)
```

`tool`은 SDK 객체이고, `raw`는 그 객체를 일반 Python dict로 펼친 중간 결과다.

```text
MCP SDK Tool 객체
  → model_dump()
  → raw dict
  → OpenAI Tool dict 조립
```

`raw`라는 이름은 “아직 필요한 부분만 골라내기 전의 원본 자료”라는 의미로 붙인 변수명이다. 특별한 Python 키워드는 아니다.

### `by_alias=True`

SDK 모델은 내부 Python 이름과 외부 프로토콜 이름이 다를 수 있다.

```text
Python 내부 이름: input_schema
외부 MCP 이름:   inputSchema
```

alias는 외부에서 사용할 별칭이다. `by_alias=True`는 `model_dump()`에게 외부 프로토콜 이름을 사용하라고 알려준다. 그래서 결과 dict에 `inputSchema`라는 키가 생긴다.

```python
raw["inputSchema"]
```

여기서 `[]`는 함수 호출이 아니다. dict에서 키로 값을 꺼내는 indexing 문법이다.

```python
raw = {
    "inputSchema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
    }
}

schema = raw["inputSchema"]
```

문자열 따옴표를 쓰는 이유는 dict의 키가 문자열이기 때문이다. `raw[inputSchema]`라고 쓰면 Python은 `inputSchema`라는 변수를 찾으므로 오류가 난다.

### `parameters`는 왜 `raw["inputSchema"]`인가?

```python
"parameters": raw["inputSchema"]
```

왼쪽 `parameters`는 OpenAI Tool 형식에서 요구하는 키다. 오른쪽 `raw["inputSchema"]`는 MCP Server가 알려준 입력 Schema다.

즉 양쪽은 이름이 달라도 의미가 연결된다.

```text
MCP의 inputSchema
  → OpenAI Tool의 parameters
```

`parameters`에 실제 입력값을 넣는 것이 아니다. “GPT가 이 함수를 호출할 때 어떤 JSON 인자를 만들어야 하는가”를 설명하는 규칙을 넣는다. 실제 값은 GPT의 `function_call.arguments`로 나중에 도착한다.

### `openai_tool`과 `route`는 왜 둘 다 필요한가?

```python
openai_tool = {
    "type": "function",
    "name": public_name,
    "description": ...,
    "parameters": raw["inputSchema"],
}

route = {
    "server": server_name,
    "tool": tool.name,
}
```

두 dict는 목적이 다르다.

| 값 | 누구를 위한 정보인가? | 예 |
| --- | --- | --- |
| `openai_tool` | GPT에게 보여주는 선택지·사용 설명서 | `travel__search_hotels`, parameters |
| `route` | Backend가 실제 MCP 목적지를 찾는 지도 | `travel` + `search_hotels` |

GPT가 `travel__search_hotels`를 선택하면 Backend는 `route`를 보고 다음을 실행한다.

```python
sessions[route["server"]].call_tool(
    route["tool"],
    arguments,
)
```

따라서 함수의 반환값은 두 개다.

```text
return (openai_tool, route)
```

`public_name`, `raw`는 반환하지 않는 중간 변수다. 함수 안에서 계산에 사용된 뒤 사라져도 되는 값이다.
