from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from vworld_client import VWorldAPIError, VWorldClient, VWorldRequestError


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = BASE_DIR / "data" / "house_with_pnu.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "house_with_coordinates.csv"
ENV_PATH = BASE_DIR / ".env"


def build_parcel_address(row: pd.Series) -> str:
    bunji = str(row["번지"]).strip()
    return f'{str(row["시도"]).strip()} {str(row["구"]).strip()} {str(row["법정동"]).strip()} {bunji}'


def enrich_coordinates(
    df: pd.DataFrame,
    client: VWorldClient,
    sleep_seconds: float = 0.0,
) -> pd.DataFrame:
    resolved_lon = []
    resolved_lat = []
    resolved_source = []
    resolved_error = []
    pnu_cache = {}
    address_cache = {}

    total = len(df)

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        lon = None
        lat = None
        source = None
        error_message = None

        pnu = row.get("PNU")
        if pd.notna(pnu):
            try:
                pnu_key = str(pnu)
                if pnu_key not in pnu_cache:
                    pnu_cache[pnu_key] = client.get_parcel_centroid_by_pnu(pnu_key)
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                result = pnu_cache[pnu_key]
                if result:
                    lon, lat = result
                    source = "pnu_centroid"
            except (VWorldAPIError, VWorldRequestError, ValueError) as exc:
                error_message = str(exc)

        if lon is None or lat is None:
            parcel_address = build_parcel_address(row)
            try:
                if parcel_address not in address_cache:
                    address_cache[parcel_address] = client.get_coordinates_from_address(
                        parcel_address,
                        address_type="PARCEL",
                    )
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                result = address_cache[parcel_address]
                if result:
                    lon, lat = result
                    source = "parcel_address"
            except (VWorldAPIError, VWorldRequestError) as exc:
                if error_message is None:
                    error_message = str(exc)

        resolved_lon.append(lon)
        resolved_lat.append(lat)
        resolved_source.append(source)
        resolved_error.append(error_message)

        if idx % 100 == 0 or idx == total:
            print(f"[{idx}/{total}] 좌표 조회 진행 중")

    result_df = df.copy()
    result_df["경도"] = resolved_lon
    result_df["위도"] = resolved_lat
    result_df["좌표조회방식"] = resolved_source
    result_df["좌표조회에러"] = resolved_error
    return result_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VWorld API로 자취방 데이터에 위도/경도 좌표를 추가합니다."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="입력 CSV 경로",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="출력 CSV 경로",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("VWORLD_API_KEY"),
        help="VWorld API 인증키. 기본값은 VWORLD_API_KEY 환경변수입니다.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="각 API 요청 timeout(초)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="요청 실패 시 재시도 횟수",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.1,
        help="요청 간 대기 시간(초). 과도한 연속 호출을 줄일 때 사용",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="테스트용으로 앞에서부터 일부 행만 처리",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ENV_PATH)
    args = parse_args()

    if not args.api_key:
        raise ValueError(
            "VWorld API 키가 없습니다. `--api-key` 옵션 또는 "
            "`VWORLD_API_KEY` 환경변수를 설정해주세요."
        )

    house_df = pd.read_csv(args.input, encoding="utf-8-sig")
    if args.limit is not None:
        house_df = house_df.head(args.limit).copy()

    client = VWorldClient(
        api_key=args.api_key,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    output_df = enrich_coordinates(
        house_df,
        client,
        sleep_seconds=args.sleep_seconds,
    )
    output_df.to_csv(args.output, index=False, encoding="utf-8-sig")

    success_count = output_df["위도"].notna().sum()
    print(f"좌표 조회 완료: {success_count}/{len(output_df)}건")
    print(f"저장 경로: {args.output}")


if __name__ == "__main__":
    main()
