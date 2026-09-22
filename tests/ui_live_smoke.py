"""Real production UI test. Requires reachable Ollama, source DB and Redis."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
out = Path('.local-test'); out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    page.goto(sys.argv[1], wait_until='networkidle')
    expect(page.get_by_role('heading', name='Travel Agent Studio')).to_be_visible()
    expect(page.get_by_role('button', name='전체 모델을 mock으로 전환')).to_have_count(0)
    expect(page.get_by_text('연결 확인', exact=True)).to_have_count(4, timeout=15000)
    visible = page.locator('body').inner_text()
    assert '54.180.117.136' not in visible and 'agent_password' not in visible
    page.get_by_role('combobox', name='Weather agent', exact=True).click()
    expect(page.get_by_role('option', name='Gemma · Ollama', exact=True)).to_be_visible()
    expect(page.get_by_role('option', name='Gemini · Google API', exact=True)).to_have_count(0)
    page.keyboard.press('Escape')
    page.get_by_role('button', name='전체 모델을 Ollama로 설정').click()
    expect(page.locator('[data-testid="stSidebar"]').get_by_text('qwen3:1.7b',exact=True)).to_have_count(4)
    expected={'weather_agent':'ollama','place_agent':'ollama','budget_agent':'ollama','validation_agent':'ollama'}
    if '--mixed' in sys.argv:
        for role,label in [('Budget agent','Gemma · Ollama'),('Validation agent','Gemma · Ollama')]:
            page.get_by_role('combobox',name=role,exact=True).click()
            page.get_by_role('option',name=label,exact=True).click()
        expected.update(budget_agent='gemma',validation_agent='gemma')
        for label,value in [('함께 숙박하는 인원','2'),('객실당 1박 계획 금액 (원)','120000'),('저녁 1인 1회 금액 (원)','20000')]:
            page.get_by_role('spinbutton',name=label,exact=True).fill(value)
            page.get_by_role('spinbutton',name=label,exact=True).press('Tab')
    page.get_by_role('button', name='멀티에이전트 실행', exact=True).click()
    expect(page.get_by_text('4개 역할 중 4개 처리', exact=True)).to_be_visible(timeout=650000)
    # Wait for final persistence too, not just role completion.
    expect(page.get_by_text('실행 기록 저장 · PostgreSQL: saved / Redis: saved', exact=True)).to_be_visible(timeout=30000)
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    with page.expect_download() as item:
        page.get_by_role('button', name='실행 결과 JSON 다운로드').click()
    run=json.loads(Path(item.value.path()).read_text(encoding='utf-8'))
    assert run['status']=='completed'
    assert not run['evidence']['facts']['is_mock'] and run['evidence']['facts']['sources']
    assert all(a['provider_used']==expected[name] and a['status']=='completed' and not a['error'] for name,a in run['agents'].items())
    if '--mixed' in sys.argv:
        assert run['budget']['items']['숙박']==60000 and run['budget']['items']['식비·카페']==80000
        assert run['budget']['total']==170000
    assert run['storage']=={'postgres':'saved','redis':'saved'}
    out.joinpath('live-production-run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2),encoding='utf-8')
    page.screenshot(path=str(out/'live-production-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    page.screenshot(path=str(out/'live-production-mobile.png'),full_page=True)
    browser.close()
print('PASS live UI: selected real models, detailed budget, sourced facts, database and Redis saved')
