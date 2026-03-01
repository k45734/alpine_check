import requests
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timezone, timedelta

# --- [설정 섹션] ---
# 1. 텔레그램 설정
TELEGRAM_TOKEN = "520599385:AAEcHtxF8Jq5Gj2ygAbidG3hdx7LRvOeB2c"
CHAT_ID = "544321507"

# 2. GitHub 트리거 설정 (Secrets에 GH_PAT 등록 필수)
GITHUB_TOKEN = os.environ.get("GH_PAT")
REPOSITORIES = [
    "k45734/alpine",
    "k45734/cupsd",
    "k45734/flask"
]

# 3. 경로 및 URL 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, 'last_alpine_info.txt')
BASE_URL = "https://dl-cdn.alpinelinux.org/alpine/"
DOCKER_API_URL = "https://hub.docker.com/v2/repositories/library/alpine/tags/latest"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def check_if_fresh(pushed_time_str):
    """도커 푸시 시간이 24시간 이내인지 확인"""
    try:
        pushed_time = datetime.fromisoformat(pushed_time_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff = now - pushed_time
        return diff < timedelta(days=1), diff
    except:
        return False, None

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, params=params, timeout=10).raise_for_status()
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {e}")

def trigger_github_actions():
    """3개 저장소에 빌드 신호 전송"""
    if not GITHUB_TOKEN:
        print("⚠️ GH_PAT이 설정되지 않아 트리거를 건너뜁니다.")
        return

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"event_type": "alpine_updated"}

    for repo in REPOSITORIES:
        url = f"https://api.github.com/repos/{repo}/dispatches"
        try:
            res = requests.post(url, headers=headers, json=data, timeout=10)
            if res.status_code == 204:
                print(f"🚀 {repo} 빌드 트리거 성공!")
            else:
                print(f"❌ {repo} 트리거 실패: {res.status_code}")
        except Exception as e:
            print(f"❌ {repo} API 요청 오류: {e}")

def get_latest_info():
    """웹 버전과 도커 해시 가져오기 (정밀 정렬 적용)"""
    try:
        # 1. 웹 버전 추출
        res = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        # vX.X 형태의 브랜치를 모두 찾음
        branches = list(set(re.findall(r'v\d+\.\d+', res.text)))
        
        # [수정] 버전 숫자를 기준으로 정렬 (예: 3.23 > 3.9)
        branches.sort(key=lambda s: [int(u) for u in s.replace('v', '').split('.')], reverse=True)
        latest_branch = branches[0]
        
        # 2. 상세 버전(v3.23.x) 추출
        rel_url = f"{BASE_URL}{latest_branch}/releases/x86_64/"
        res_rel = requests.get(rel_url, headers=HEADERS, timeout=10)
        full_versions = list(set(re.findall(r'\b\d+\.\d+\.\d+\b', res_rel.text)))
        
        # [수정] 상세 버전도 숫자 기준으로 정렬
        full_versions.sort(key=lambda s: [int(u) for u in s.split('.')], reverse=True)
        web_v = full_versions[0] if full_versions else latest_branch.replace('v', '')

        # 3. 도커 정보 추출
        res_docker = requests.get(DOCKER_API_URL, headers=HEADERS, timeout=10).json()
        digest = res_docker.get('digest') or res_docker['images'][0]['digest']
        pushed_at = res_docker.get('last_updated')

        return web_v, digest, pushed_at
    except Exception as e:
        print(f"❌ 데이터 수집 실패: {e}")
        return None, None, None

def main():
    web_v, digest, docker_time = get_latest_info()
    if not web_v or not digest: return

    last_info = ""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f: last_info = f.read().strip()

    current_info = f"{web_v}|{digest}"

    if current_info != last_info:
        is_fresh, diff = check_if_fresh(docker_time)
        msg = f"🔔 *Alpine Linux 업데이트 감지!*\n\n" \
              f"🌐 *웹 버전:* `v{web_v}`\n" \
              f"🐳 *도커 해시:* `{digest[:12]}...`\n" \
              f"📅 *푸시 시간:* {docker_time}\n"
        
        if is_fresh:
            msg += f"\n✨ **상태: 최신 빌드 확인됨!**\n🚀 하위 프로젝트 빌드를 시작합니다."
            trigger_github_actions()
        else:
            msg += f"\n⚠️ **상태: 도커 빌드 지연 중**\n이미지가 아직 업데이트되지 않았을 수 있습니다."

        send_telegram_message(msg)
        with open(VERSION_FILE, "w") as f: f.write(current_info)
    else:
        print(f"✅ 변동 없음 (v{web_v})")

if __name__ == "__main__":
    main()