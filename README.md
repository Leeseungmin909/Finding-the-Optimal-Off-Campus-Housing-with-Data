# Finding the Optimal Off-Campus Housing with Data

부산 지역 자취방 데이터를 정제하고, 공간정보 오픈 API(VWorld)와 지도 시각화를 결합해
최적 자취방 후보를 분석하는 프로젝트입니다.

## 현재 구현된 흐름

1. `data.py`
   원본 자취방/버스/CCTV/지하철 데이터를 정제해 `cleaned_*.csv`로 저장합니다.
2. `src/pnu_generator.py`
   자취방 주소를 기반으로 법정동코드와 PNU를 생성합니다.
3. `src/enrich_house_coordinates.py`
   VWorld API를 호출해 자취방별 위도/경도를 조회하고 `house_with_coordinates.csv`로 저장합니다.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## API 키 관리

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 VWorld API 키를 넣어두면 됩니다.

```bash
cp .env .env
```

`.env`

```env
VWORLD_API_KEY=YOUR_VWORLD_API_KEY
```

## 실행 순서

```bash
python3 data.py
python3 src/pnu_generator.py
python3 src/enrich_house_coordinates.py --limit 100
```

필요하면 일회성으로 `--api-key` 옵션을 직접 넘길 수도 있습니다.

대량 데이터 전체 실행 전에는 먼저 일부 샘플로 테스트하는 것을 권장합니다.

```bash
python3 src/enrich_house_coordinates.py --limit 100 --query-strategy address_only --timeout 20 --max-retries 3 --sleep-seconds 0.05
python3 src/enrich_house_coordinates.py --query-strategy address_only --timeout 20 --max-retries 3 --sleep-seconds 0.05
```

## 좌표 조회 전략

- 1순위: `PNU` 기반 연속지적도 조회 후 필지 중심점 계산
- 2순위: `시도 + 구 + 법정동 + 번지` 조합의 지번 주소로 좌표 조회
- 출력 좌표계: `EPSG:4326` 기준 `경도`, `위도`

## 다음 단계

다음 구현 단계에서는 `house_with_coordinates.csv`를 이용해 Folium 기반 히트맵과
후보 자취방 마커 시각화를 연결할 수 있습니다.

## Folium 지도 생성

아래 스크립트는 자취방 좌표, 버스 정류장, CCTV 데이터를 이용해
`최적 자취방 히트맵`과 `상위 후보 마커`가 포함된 HTML 지도를 생성합니다.

```bash
python3 src/generate_folium_map.py --top-n 20
```

생성 결과:

- `outputs/optimal_room_map.html`
- `outputs/optimal_room_scores.csv`

평가 점수는 아래 요소를 가중합해서 계산합니다.

- 월세가 낮을수록 가산점
- 보증금이 낮을수록 가산점
- 전용면적이 넓을수록 가산점
- 건축년도가 최근일수록 가산점
- 주변 버스 정류장 수가 많을수록 가산점
- 주변 CCTV 수가 많을수록 가산점
