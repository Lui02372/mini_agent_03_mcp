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
    page.get_by_role('button', name='전체 모델을 Ollama로 설정').click()
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
    assert all(a['provider_used']=='ollama' and a['status']=='completed' and not a['error'] for a in run['agents'].values())
    assert run['storage']=={'postgres':'saved','redis':'saved'}
    out.joinpath('live-production-run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2),encoding='utf-8')
    page.screenshot(path=str(out/'live-production-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    page.screenshot(path=str(out/'live-production-mobile.png'),full_page=True)
    browser.close()
print('PASS live UI: four real Ollama roles, sourced facts, database and Redis saved')
