import requests
from bs4 import BeautifulSoup
import re
import os

# --- 설정 (기본 정보 유지) ---
TELEGRAM_TOKEN = "520599385:AAEcHtxF8Jq5Gj2ygAbidG3hdx7LRvOeB2c"
CHAT_ID = "544321507"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, 'last_alpine_info.txt')
BASE_URL = "https://dl-cdn.alpinelinux.org/alpine/"
DOCKER_API_URL = "https://hub.docker.com/v2/repositories/library/alpine/tags/latest"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
from datetime import datetime, timezone, timedelta
def trigger_all_builds():
    """목록에 있는 모든 저장소의 GitHub Actions를 실행시킵니다."""
    token = os.environ.get("GH_PAT")
    # 트리거할 저장소 목록
    repositories = [
        "k45734/alpine",
        "k45734/cupsd",
        "k45734/flask"
    ]
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {"event_type": "alpine_updated"} # 모든 저장소의 YAML에서 이 이름을 사용하면 됩니다.

    for repo in repositories:
        url = f"https://api.github.com/repos/{repo}/dispatches"
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 204:
                print(f"🚀 {repo} 빌드 트리거 성공!")
            else:
                print(f"❌ {repo} 트리거 실패: {response.status_code}")
        except Exception as e:
            print(f"❌ {repo} 요청 중 오류 발생: {e}")
			
def check_if_fresh(pushed_time_str):
    """푸시된 시간이 24시간 이내인지 확인합니다."""
    try:
        # 도커 허브 시간 형식 (ISO 8601) 파싱
        # Z는 UTC를 의미하므로 이를 고려하여 변환
        pushed_time = datetime.fromisoformat(pushed_time_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        
        # 차이 계산
        diff = now - pushed_time
        
        # 24시간(86400초) 이내면 True
        if diff < timedelta(days=1):
            return True, diff
        return False, diff
    except:
        return False, None
def send_telegram_message(message):
    """텔레그램으로 메시지를 전송합니다."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {e}")

def get_web_latest_version():
    """알파인 배포 서버에서 최신 상세 버전을 가져옵니다."""
    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        res.raise_for_status()
        
        # 'vX.X' 형태의 브랜치 찾기
        raw_branches = re.findall(r'v\d+\.\d+/?', res.text)
        clean_branches = sorted(list(set([b.strip('/') for b in raw_branches])), 
                                key=lambda s: list(map(int, s.replace('v','').split('.'))), 
                                reverse=True)
        
        if not clean_branches:
            print("❌ 웹: 브랜치 패턴을 찾을 수 없습니다.")
            return None
            
        latest_branch = clean_branches[0]
        
        # 상세 버전 찾기
        rel_url = f"{BASE_URL}{latest_branch}/releases/x86_64/"
        res_rel = requests.get(rel_url, headers=HEADERS, timeout=10)
        full_versions = set(re.findall(r'\b\d+\.\d+\.\d+\b', res_rel.text))
        
        if not full_versions:
            return latest_branch.replace('v', '')
        
        return sorted(list(full_versions), key=lambda s: list(map(int, s.split('.'))), reverse=True)[0]
    except Exception as e:
        print(f"❌ 웹 데이터 가져오기 실패: {e}")
        return None

def get_docker_latest_info():
    """도커 허브에서 이미지 해시와 업데이트 시간을 가져옵니다."""
    try:
        res = requests.get(DOCKER_API_URL, headers=HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        digest = data.get('digest') or data['images'][0]['digest']
        last_pushed = data.get('last_updated')
        return digest, last_pushed
    except Exception as e:
        print(f"❌ 도커 허브 데이터 가져오기 실패: {e}")
        return None, None

def main():
    print("🔍 업데이트 확인 중...")
    web_version = get_web_latest_version()
    docker_digest, docker_time = get_docker_latest_info()
    
    if not web_version or not docker_digest:
        print("⚠️ 일부 데이터를 가져오지 못했습니다. 네트워크 상태를 확인하세요.")
        return

    # 기록 읽기 (버전|해시)
    last_info = ""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            last_info = f.read().strip()

    current_info = f"{web_version}|{docker_digest}"

    if current_info != last_info:
        old_version = last_info.split('|')[0] if last_info else "없음"
        old_digest = last_info.split('|')[1] if '|' in last_info else "없음"
        is_fresh, time_diff = check_if_fresh(docker_time)
        msg = f"🔔 *Alpine Linux 업데이트 감지!*\n\n"
        msg += f"🌐 *웹 배포 버전:* `v{web_version}` (이전: v{old_version})\n"
        msg += f"🐳 *도커 최신 해시:* `{docker_digest[:12]}...`\n"
        msg += f"📅 *도커 푸시 시간:* {docker_time}\n\n"
        
        if is_fresh:
            msg += f"\n✨ **상태: 진짜 최신! (약 {time_diff.seconds // 3600}시간 전 업데이트)**\n"
            msg += "✅ 안심하고 `docker pull` 하셔도 됩니다!"
        else:
            msg += f"\n⚠️ **상태: 시차 발생 중 (마지막 업데이트가 {time_diff.days}일 전)**\n"
            msg += "❌ 웹 버전은 올라갔지만, 도커 이미지는 아직 빌드 중일 수 있습니다."
        print(msg)
        send_telegram_message(msg)
        trigger_all_builds()
        with open(VERSION_FILE, "w") as f:
            f.write(current_info)
    else:
        print(f"✅ 변동 없음 (v{web_version} / {docker_digest[:12]})")

if __name__ == "__main__":
    main()