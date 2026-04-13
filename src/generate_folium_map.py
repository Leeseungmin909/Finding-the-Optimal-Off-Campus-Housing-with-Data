from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise ImportError(
        "folium이 설치되어 있지 않습니다. `pip install -r requirements.txt`를 먼저 실행해주세요."
    ) from exc


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HOUSE_PATH = BASE_DIR / "data" / "house_with_coordinates.csv"
DEFAULT_BUS_PATH = BASE_DIR / "data" / "cleaned_BUS.csv"
DEFAULT_CCTV_PATH = BASE_DIR / "data" / "cleaned_CCTV.csv"
DEFAULT_OUTPUT_PATH = BASE_DIR / "outputs" / "optimal_room_map.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Folium 기반 최적 자취방 지도(히트맵 + 마커)를 생성합니다."
    )
    parser.add_argument("--house-path", default=str(DEFAULT_HOUSE_PATH), help="자취방 CSV 경로")
    parser.add_argument("--bus-path", default=str(DEFAULT_BUS_PATH), help="버스 CSV 경로")
    parser.add_argument("--cctv-path", default=str(DEFAULT_CCTV_PATH), help="CCTV CSV 경로")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="출력 HTML 경로")
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="마커로 강조할 상위 자취방 개수",
    )
    parser.add_argument(
        "--bus-radius",
        type=float,
        default=0.0045,
        help="버스 정류장 근접도 계산 반경(위경도 degree 단위, 기본 약 500m)",
    )
    parser.add_argument(
        "--cctv-radius",
        type=float,
        default=0.0030,
        help="CCTV 근접도 계산 반경(위경도 degree 단위, 기본 약 330m)",
    )
    return parser.parse_args()


def load_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def sanitize_coordinate_columns(df: pd.DataFrame) -> pd.DataFrame:
    sanitized = df.copy()
    sanitized["위도"] = pd.to_numeric(sanitized["위도"], errors="coerce")
    sanitized["경도"] = pd.to_numeric(sanitized["경도"], errors="coerce")
    sanitized = sanitized.dropna(subset=["위도", "경도"]).copy()
    return sanitized


def parse_money(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .replace({"": np.nan, "nan": np.nan})
        .astype(float)
    )


def normalize(series: pd.Series, inverse: bool = False) -> pd.Series:
    series = series.astype(float)
    min_value = series.min()
    max_value = series.max()

    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        normalized = pd.Series(1.0, index=series.index)
    else:
        normalized = (series - min_value) / (max_value - min_value)

    return 1 - normalized if inverse else normalized


def count_nearby_points(
    house_df: pd.DataFrame,
    point_df: pd.DataFrame,
    radius: float,
) -> np.ndarray:
    if point_df.empty:
        return np.zeros(len(house_df), dtype=int)

    house_lat = house_df["위도"].to_numpy()
    house_lon = house_df["경도"].to_numpy()
    point_lat = point_df["위도"].to_numpy()
    point_lon = point_df["경도"].to_numpy()

    counts = []
    for lat, lon in zip(house_lat, house_lon):
        lat_mask = np.abs(point_lat - lat) <= radius
        lon_mask = np.abs(point_lon - lon) <= radius
        counts.append(int(np.count_nonzero(lat_mask & lon_mask)))
    return np.array(counts)


def prepare_house_scores(
    house_df: pd.DataFrame,
    bus_df: pd.DataFrame,
    cctv_df: pd.DataFrame,
    bus_radius: float,
    cctv_radius: float,
) -> pd.DataFrame:
    df = sanitize_coordinate_columns(house_df)

    df["보증금_정수"] = parse_money(df["보증금(만원)"])
    df["월세_정수"] = parse_money(df["월세금(만원)"])
    df["전용면적_정수"] = pd.to_numeric(df["전용면적(㎡)"], errors="coerce")
    df["건축년도_정수"] = pd.to_numeric(df["건축년도"], errors="coerce")

    bus_points = sanitize_coordinate_columns(bus_df)
    cctv_points = sanitize_coordinate_columns(cctv_df)

    df["주변버스정류장수"] = count_nearby_points(df, bus_points, bus_radius)
    df["주변CCTV수"] = count_nearby_points(df, cctv_points, cctv_radius)

    df["score_deposit"] = normalize(df["보증금_정수"], inverse=True)
    df["score_monthly_rent"] = normalize(df["월세_정수"], inverse=True)
    df["score_area"] = normalize(df["전용면적_정수"])
    df["score_building_year"] = normalize(df["건축년도_정수"])
    df["score_bus_access"] = normalize(df["주변버스정류장수"])
    df["score_cctv_safety"] = normalize(df["주변CCTV수"])

    df["최적점수"] = (
        0.20 * df["score_monthly_rent"]
        + 0.15 * df["score_deposit"]
        + 0.20 * df["score_area"]
        + 0.10 * df["score_building_year"]
        + 0.20 * df["score_bus_access"]
        + 0.15 * df["score_cctv_safety"]
    )

    return df.sort_values("최적점수", ascending=False).reset_index(drop=True)


def format_popup_html(row: pd.Series) -> str:
    score = round(float(row["최적점수"]), 3)
    deposit = row["보증금(만원)"]
    monthly = row["월세금(만원)"]
    area = round(float(row["전용면적_정수"]), 2)
    year = int(row["건축년도_정수"]) if pd.notna(row["건축년도_정수"]) else "-"

    return f"""
    <div style="width:260px;">
      <h4 style="margin-bottom:8px;">{row['건물명']}</h4>
      <p style="margin:2px 0;"><b>주소</b>: {row['시군구']} {row['번지']}</p>
      <p style="margin:2px 0;"><b>유형</b>: {row['전월세구분']}</p>
      <p style="margin:2px 0;"><b>보증금 / 월세</b>: {deposit} / {monthly}</p>
      <p style="margin:2px 0;"><b>면적</b>: {area}㎡</p>
      <p style="margin:2px 0;"><b>건축년도</b>: {year}</p>
      <p style="margin:2px 0;"><b>주변 버스</b>: {int(row['주변버스정류장수'])}개</p>
      <p style="margin:2px 0;"><b>주변 CCTV</b>: {int(row['주변CCTV수'])}개</p>
      <p style="margin:6px 0 0;"><b>최적점수</b>: {score}</p>
    </div>
    """


def add_top_room_markers(
    fmap: folium.Map,
    scored_df: pd.DataFrame,
    top_n: int,
) -> None:
    top_df = scored_df.head(top_n)
    cluster = MarkerCluster(name=f"상위 {top_n}개 자취방").add_to(fmap)

    for rank, (_, row) in enumerate(top_df.iterrows(), start=1):
        popup = folium.Popup(format_popup_html(row), max_width=320)
        tooltip = f"{rank}위 {row['건물명']} | 점수 {row['최적점수']:.3f}"
        folium.Marker(
            location=[row["위도"], row["경도"]],
            popup=popup,
            tooltip=tooltip,
            icon=folium.Icon(color="red", icon="home", prefix="fa"),
        ).add_to(cluster)


def add_reference_layers(
    fmap: folium.Map,
    bus_df: pd.DataFrame,
    cctv_df: pd.DataFrame,
) -> None:
    bus_df = sanitize_coordinate_columns(bus_df)
    cctv_df = sanitize_coordinate_columns(cctv_df)

    bus_group = folium.FeatureGroup(name="버스 정류장", show=False)
    for _, row in bus_df.head(500).iterrows():
        folium.CircleMarker(
            location=[row["위도"], row["경도"]],
            radius=2,
            color="#1565c0",
            fill=True,
            fill_opacity=0.55,
            weight=1,
            tooltip=row.get("정류장명", "버스 정류장"),
        ).add_to(bus_group)
    bus_group.add_to(fmap)

    cctv_group = folium.FeatureGroup(name="CCTV", show=False)
    for _, row in cctv_df.head(1000).iterrows():
        folium.CircleMarker(
            location=[row["위도"], row["경도"]],
            radius=1.5,
            color="#2e7d32",
            fill=True,
            fill_opacity=0.35,
            weight=0,
        ).add_to(cctv_group)
    cctv_group.add_to(fmap)


def add_heatmap(fmap: folium.Map, scored_df: pd.DataFrame) -> None:
    heat_data = scored_df[["위도", "경도", "최적점수"]].values.tolist()
    HeatMap(
        heat_data,
        name="최적 자취방 히트맵",
        min_opacity=0.35,
        radius=18,
        blur=14,
        max_zoom=14,
    ).add_to(fmap)


def create_map(
    scored_df: pd.DataFrame,
    bus_df: pd.DataFrame,
    cctv_df: pd.DataFrame,
    top_n: int,
) -> folium.Map:
    center_lat = float(scored_df["위도"].mean())
    center_lon = float(scored_df["경도"].mean())

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    add_heatmap(fmap, scored_df)
    add_top_room_markers(fmap, scored_df, top_n)
    add_reference_layers(fmap, bus_df, cctv_df)
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def main() -> None:
    args = parse_args()

    house_df = load_csv(args.house_path)
    bus_df = load_csv(args.bus_path)
    cctv_df = load_csv(args.cctv_path)

    scored_df = prepare_house_scores(
        house_df=house_df,
        bus_df=bus_df,
        cctv_df=cctv_df,
        bus_radius=args.bus_radius,
        cctv_radius=args.cctv_radius,
    )
    fmap = create_map(scored_df, bus_df, cctv_df, args.top_n)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))

    score_output_path = output_path.with_name("optimal_room_scores.csv")
    scored_df.to_csv(score_output_path, index=False, encoding="utf-8-sig")

    print(f"지도 저장 완료: {output_path}")
    print(f"점수 데이터 저장 완료: {score_output_path}")
    print(f"상위 후보 수: {min(args.top_n, len(scored_df))}")


if __name__ == "__main__":
    main()
