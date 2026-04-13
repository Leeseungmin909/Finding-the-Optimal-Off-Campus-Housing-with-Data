from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from vworld_client import VWorldAPIError, VWorldClient


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = BASE_DIR / "data" / "house_with_pnu.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "house_with_coordinates.csv"
ENV_PATH = BASE_DIR / ".env"


def build_parcel_address(row: pd.Series) -> str:
    bunji = str(row["번지"]).strip()
    return f'{str(row["시도"]).strip()} {str(row["구"]).strip()} {str(row["법정동"]).strip()} {bunji}'


def enrich_coordinates(df: pd.DataFrame, client: VWorldClient) -> pd.DataFrame:
    resolved_lon = []
    resolved_lat = []
    resolved_source = []

    for _, row in df.iterrows():
        lon = None
        lat = None
        source = None

        pnu = row.get("PNU")
        if pd.notna(pnu):
            try:
                result = client.get_parcel_centroid_by_pnu(str(pnu))
                if result:
                    lon, lat = result
                    source = "pnu_centroid"
            except (VWorldAPIError, ValueError):
                pass

        if lon is None or lat is None:
            parcel_address = build_parcel_address(row)
            try:
                result = client.get_coordinates_from_address(
                    parcel_address,
                    address_type="PARCEL",
                )
                if result:
                    lon, lat = result
                    source = "parcel_address"
            except VWorldAPIError:
                pass

        resolved_lon.append(lon)
        resolved_lat.append(lat)
        resolved_source.append(source)

    result_df = df.copy()
    result_df["경도"] = resolved_lon
    result_df["위도"] = resolved_lat
    result_df["좌표조회방식"] = resolved_source
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
    client = VWorldClient(api_key=args.api_key)
    output_df = enrich_coordinates(house_df, client)
    output_df.to_csv(args.output, index=False, encoding="utf-8-sig")

    success_count = output_df["위도"].notna().sum()
    print(f"좌표 조회 완료: {success_count}/{len(output_df)}건")
    print(f"저장 경로: {args.output}")


if __name__ == "__main__":
    main()
