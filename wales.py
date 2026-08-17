from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from math import inf
from typing import Dict, List, Optional, Tuple

from solver_search import DEFAULT_SEARCH_POLICY

evaluate_count = 0
evaluate_total_time = 0.0
allocate_call_count = 0
allocate_total_time = 0.0

DEBUG = False
logger = print

WALER_ADJUSTMENT_LENGTHS = (0, 100, 150, 200, 300)
WALER_MAX_GAP = 199


def resolve_tail_adjustment(
    required_length: int,
    *,
    steel_length: Optional[int] = None,
    adjustment_lengths: Tuple[int, ...] = WALER_ADJUSTMENT_LENGTHS,
    max_gap: int = WALER_MAX_GAP,
    steel_step: int = 500,
) -> Tuple[int, int, int]:
    """Return ``(steel_length, adjustment, gap)`` for a Waler tail.

    Formal Waler steel remains on the standard material grid.  One adjustment
    block is placed after the final steel member and the remaining 0..max_gap
    millimetres are left for field treatment.
    """

    required_length = int(round(required_length))
    if required_length < 0:
        raise ValueError("required_length must not be negative")
    if required_length == 0:
        return 0, 0, 0
    if max_gap < 0:
        raise ValueError("max_gap must not be negative")
    if steel_step <= 0:
        raise ValueError("steel_step must be positive")

    normalized_adjustments = tuple(
        sorted({int(round(value)) for value in adjustment_lengths if value >= 0})
    )
    if not normalized_adjustments:
        raise ValueError("at least one adjustment length is required")

    options: List[Tuple[int, int, int]] = []
    if steel_length is None:
        for adjustment in normalized_adjustments:
            for gap in range(max_gap + 1):
                target = required_length - adjustment - gap
                if target >= 0 and target % steel_step == 0:
                    options.append((target, adjustment, gap))
    else:
        target = int(round(steel_length))
        for adjustment in normalized_adjustments:
            gap = required_length - target - adjustment
            if 0 <= gap <= max_gap:
                options.append((target, adjustment, gap))

    if not options:
        raise ValueError(
            "Waler length cannot be completed by one adjustment block "
            f"with a 0..{max_gap} mm field remainder"
        )

    # Prefer the smallest field remainder; when it is equal, use the smaller
    # adjustment block.  With the standard list and max_gap=199 every 500 mm
    # residue has at least one legal option.
    return min(options, key=lambda item: (item[2], item[1], -item[0]))


def debug_print(*args) -> None:
    if DEBUG:
        print(*args)


def set_logger(func) -> None:
    global logger
    logger = func


def generate_candidate_joint_points(
    total_length: int,
    min_piece_length: int,
    step: int = 500,
) -> List[int]:
    """Generate candidate joint positions every `step` from min_piece_length to total_length - min_piece_length."""
    if total_length < 2 * min_piece_length:
        return []
    return list(range(min_piece_length, total_length - min_piece_length + 1, step))

# =========================
# 1. 設定區
# =========================

@dataclass
class Config:
    # 幾何需求
    total_length: int
    support_points: List[int]
    candidate_joint_points: List[int] = field(default_factory=list)

    # 長度限制
    min_piece_length: int = 1000
    preferred_min_piece_length: int = 4000
    max_piece_length: int = 10000
    joint_clearance_to_support: int = 300
    candidate_joint_step: int = 500
    purchasable_lengths: List[int] = field(default_factory=list)
    adjustment_lengths: Tuple[int, ...] = WALER_ADJUSTMENT_LENGTHS
    max_gap: int = WALER_MAX_GAP
    steel_target_length: int = field(init=False)
    tail_adjustment: int = field(init=False)
    tail_gap: int = field(init=False)

    # 短/中/長段分類範圍
    short_segment_min: int = 4000
    short_segment_max: int = 6000
    mid_segment_min: int = 6000
    mid_segment_max: int = 8000
    long_segment_min: int = 8000
    long_segment_max: int = 10000

    # 最佳段長比例設定
    short_segment_ratio_target: float = 0.2
    mid_segment_ratio_target: float = 0.5
    long_segment_ratio_target: float = 0.3
    ratio_penalty_weight: float = 100_000



    # GA 參數
    population_size: int = DEFAULT_SEARCH_POLICY.waler_search_stages[0].population_size
    generations: int = DEFAULT_SEARCH_POLICY.waler_search_stages[0].generations
    crossover_rate: float = 0.85
    mutation_rate: float = 0.08
    elite_size: int = 8
    tournament_k: int = 4

    def __post_init__(self) -> None:
        (
            self.steel_target_length,
            self.tail_adjustment,
            self.tail_gap,
        ) = resolve_tail_adjustment(
            self.total_length,
            adjustment_lengths=self.adjustment_lengths,
            max_gap=self.max_gap,
            steel_step=self.candidate_joint_step,
        )

        if not self.candidate_joint_points:
            self.candidate_joint_points = generate_candidate_joint_points(
                self.steel_target_length,
                self.min_piece_length,
                self.candidate_joint_step,
            )

        if not self.purchasable_lengths:
            self.purchasable_lengths = list(range(
                self.min_piece_length,
                self.max_piece_length + 1,
                self.candidate_joint_step,
            ))

    # 輸出
    top_n: int = 5

# =========================
# 2. 基本工具函式
# =========================

import tkinter as tk
from tkinter import messagebox
from typing import List, Dict, Optional



def get_initial_config_from_gui(
    default_total_length: int,
    default_support_points: List[int],
) -> Optional[Dict[str, object]]:
    """
    跳出 GUI 視窗，讓使用者輸入總長度、支撐點與短/中/長段比例設定。

    - total_length: 單件總長度
    - support_points: 以逗號或空白分隔的支撐點位置
    - 目標比例: 20%、50%、30%
    """
    result: Dict[str, object] = {}

    root = tk.Tk()
    root.title("總長度與支撐點設定")
    root.geometry("580x620")

    tk.Label(root, text="請輸入總長度", font=("Arial", 12, "bold")).pack(pady=(12, 4))
    total_length_entry = tk.Entry(root, width=20, font=("Arial", 12))
    total_length_entry.insert(0, str(default_total_length))
    total_length_entry.pack(pady=(0, 12))

    tk.Label(root, text="請輸入支撐點位置（逗號、空白或換行分隔）", font=("Arial", 12, "bold")).pack(pady=(0, 4))
    support_points_text = tk.Text(root, width=72, height=10, font=("Arial", 11))
    support_points_text.insert("1.0", ", ".join(str(p) for p in default_support_points))
    support_points_text.pack(padx=10, pady=(0, 12))

    tk.Label(root, text="短/中/長段目標比例（固定區間：短段 4000~6000，中段 6000~8000，長段 8000~10000）", font=("Arial", 12, "bold"), wraplength=560).pack(pady=(8, 4))
    ratio_frame = tk.Frame(root)
    ratio_frame.pack(padx=10, pady=(0, 12), fill="x")

    tk.Label(ratio_frame, text="短段", width=12, anchor="w").grid(row=0, column=0, padx=5, pady=3)
    short_ratio_entry = tk.Entry(ratio_frame, width=12)
    short_ratio_entry.insert(0, "20")
    short_ratio_entry.grid(row=0, column=1, padx=5, pady=3)

    tk.Label(ratio_frame, text="中段", width=12, anchor="w").grid(row=1, column=0, padx=5, pady=3)
    mid_ratio_entry = tk.Entry(ratio_frame, width=12)
    mid_ratio_entry.insert(0, "50")
    mid_ratio_entry.grid(row=1, column=1, padx=5, pady=3)

    tk.Label(ratio_frame, text="長段", width=12, anchor="w").grid(row=2, column=0, padx=5, pady=3)
    long_ratio_entry = tk.Entry(ratio_frame, width=12)
    long_ratio_entry.insert(0, "30")
    long_ratio_entry.grid(row=2, column=1, padx=5, pady=3)

    message_label = tk.Label(root, text="", fg="red", font=("Arial", 10))
    message_label.pack()

    def on_confirm():
        text_value = total_length_entry.get().strip()
        if not text_value:
            message_label.config(text="請輸入總長度")
            return

        try:
            total_length = int(text_value)
            if total_length <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("輸入錯誤", "總長度必須是大於 0 的整數")
            return

        support_text = support_points_text.get("1.0", "end").strip()
        if support_text == "":
            support_points: List[int] = []
        else:
            normalized = support_text.replace(",", " ").replace("\n", " ")
            parts = [p for p in normalized.split() if p]
            support_points = []
            for part in parts:
                try:
                    value = int(part)
                    support_points.append(value)
                except ValueError:
                    messagebox.showerror(
                        "輸入錯誤",
                        f"支撐點 {part} 不是有效整數"
                    )
                    return

        try:
            short_ratio = float(short_ratio_entry.get().strip())
            mid_ratio = float(mid_ratio_entry.get().strip())
            long_ratio = float(long_ratio_entry.get().strip())
        except ValueError:
            messagebox.showerror("輸入錯誤", "段長目標比例必須為數字")
            return

        if short_ratio < 0 or mid_ratio < 0 or long_ratio < 0:
            messagebox.showerror("輸入錯誤", "目標比例不能是負數")
            return

        if short_ratio > 1 or mid_ratio > 1 or long_ratio > 1:
            short_ratio /= 100.0 if short_ratio > 1 else 1.0
            mid_ratio /= 100.0 if mid_ratio > 1 else 1.0
            long_ratio /= 100.0 if long_ratio > 1 else 1.0

        total_ratio = short_ratio + mid_ratio + long_ratio
        if total_ratio <= 0:
            messagebox.showerror("輸入錯誤", "短/中/長段目標比例總和必須大於 0")
            return

        short_ratio /= total_ratio
        mid_ratio /= total_ratio
        long_ratio /= total_ratio

        result["total_length"] = total_length
        result["support_points"] = sorted(set(support_points))
        result["short_segment_ratio_target"] = short_ratio
        result["mid_segment_ratio_target"] = mid_ratio
        result["long_segment_ratio_target"] = long_ratio
        root.destroy()

    def on_cancel():
        result["total_length"] = None
        result["support_points"] = []
        root.destroy()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    confirm_btn = tk.Button(button_frame, text="確定", width=12, command=on_confirm)
    confirm_btn.grid(row=0, column=0, padx=10)

    cancel_btn = tk.Button(button_frame, text="取消", width=12, command=on_cancel)
    cancel_btn.grid(row=0, column=1, padx=10)

    root.mainloop()

    if "total_length" not in result:
        return None
    return {
        "total_length": result["total_length"],
        "support_points": result["support_points"],
        "short_segment_ratio_target": result["short_segment_ratio_target"],
        "mid_segment_ratio_target": result["mid_segment_ratio_target"],
        "long_segment_ratio_target": result["long_segment_ratio_target"],
    }


def get_stock_items_from_gui(
    lengths: List[int],
    default_qty_map: Optional[Dict[int, int]] = None
) -> Optional[List[Dict]]:
    """
    跳出 GUI 視窗，讓使用者輸入各長度的數量。

    參數：
    - lengths: 可選長度清單，例如 [4000, 4500, ..., 10000]
    - default_qty_map: 每個長度的預設數量，例如：
        {
            4000: 10,
            4500: 8,
            5000: 12,
            ...
        }

    回傳格式：
    [
        {"id": "A4000", "length": 4000, "qty": 2},
        ...
    ]

    如果取消，回傳 None
    """
    if default_qty_map is None:
        default_qty_map = {}

    result = {"stock_items": None}

    root = tk.Tk()
    root.title("庫存料輸入")
    root.geometry("360x650")

    title_label = tk.Label(root, text="請輸入各長度庫存數量", font=("Arial", 12, "bold"))
    title_label.pack(pady=10)

    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=5)

    tk.Label(frame, text="長度(mm)", width=12, anchor="w").grid(row=0, column=0, padx=5, pady=5)
    tk.Label(frame, text="數量", width=10, anchor="w").grid(row=0, column=1, padx=5, pady=5)

    entry_widgets = {}

    for i, length in enumerate(lengths, start=1):
        tk.Label(frame, text=str(length), width=12, anchor="w").grid(row=i, column=0, padx=5, pady=3)

        entry = tk.Entry(frame, width=10)

        default_qty = default_qty_map.get(length, 0)
        entry.insert(0, str(default_qty))

        entry.grid(row=i, column=1, padx=5, pady=3)
        entry_widgets[length] = entry

    def on_confirm():
        stock_items = []

        for length in lengths:
            text = entry_widgets[length].get().strip()

            if text == "":
                qty = 0
            else:
                try:
                    qty = int(text)
                except ValueError:
                    messagebox.showerror("輸入錯誤", f"長度 {length} 的數量不是整數")
                    return

            if qty < 0:
                messagebox.showerror("輸入錯誤", f"長度 {length} 的數量不能是負數")
                return

            if qty > 0:
                stock_items.append({
                    "id": f"A{length}",
                    "length": length,
                    "qty": qty,
                })

        result["stock_items"] = stock_items
        root.destroy()

    def on_cancel():
        result["stock_items"] = None
        root.destroy()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=15)

    confirm_btn = tk.Button(button_frame, text="確定", width=10, command=on_confirm)
    confirm_btn.grid(row=0, column=0, padx=10)

    cancel_btn = tk.Button(button_frame, text="取消", width=10, command=on_cancel)
    cancel_btn.grid(row=0, column=1, padx=10)

    root.mainloop()

    return result["stock_items"]


def classify_length(length: int, cfg: Config) -> str:
    """把段長分類成 short / mid / long。

    依據目標區間:
    - short: 4000 <= len < 6000
    - mid: 6000 <= len <= 8000
    - long: 8000 < len <= 10000
    """
    if cfg.short_segment_min <= length < cfg.short_segment_max:
        return "short"
    elif cfg.mid_segment_min <= length <= cfg.mid_segment_max:
        return "mid"
    elif cfg.long_segment_min < length <= cfg.long_segment_max:
        return "long"
    return "out"


def is_joint_allowed(point: int, cfg: Config) -> bool:
    """檢查接頭位置是否離支撐點太近。"""
    for support in cfg.support_points:
        if abs(point - support) < cfg.joint_clearance_to_support:
            return False
    return True


def expand_stock_items(stock_items: List[Dict]) -> List[Dict]:
    """
    把庫存展開成單支清單。
    例如:
    [{"id":"A2", "length":9500, "qty":2}]
    ->
    [{"stock_id":"A2#1","stock_group":"A2","stock_length":9500},
     {"stock_id":"A2#2","stock_group":"A2","stock_length":9500}]
    """
    inventory = []
    for item in stock_items:
        item_id = item.get("id", str(item["length"]))
        length = item["length"]
        qty = item["qty"]
        for i in range(qty):
            inventory.append(
                {
                    "stock_id": f"{item_id}#{i+1}",
                    "stock_group": item_id,
                    "stock_length": length,
                }
            )
    return inventory


# =========================
# 3. 染色體 <-> 分段
# =========================

def decode_individual(individual: List[int], cfg: Config) -> Tuple[List[int], List[int]]:
    """
    染色體 = 每個候選點是否選為接頭 (0/1)
    回傳:
    - joints: 真正採用的接頭位置
    - segments: 分段長度
    """
    selected_joints = []

    for gene, point in zip(individual, cfg.candidate_joint_points):
        if gene == 1:
            selected_joints.append(point)

    selected_joints = sorted(set(selected_joints))

    # 加入終點，方便算 segment
    all_points = [0] + selected_joints + [cfg.steel_target_length]

    segments = []
    for i in range(len(all_points) - 1):
        segments.append(all_points[i + 1] - all_points[i])

    return selected_joints, segments


def validate_segments(joints: List[int], segments: List[int], cfg: Config) -> Tuple[bool, List[str]]:
    """
    驗證是否符合基本規則。
    回傳:
    - 是否有效
    - 錯誤訊息清單
    """
    errors = []

    # 本工程不允許裁切材料，因此每段長度必須剛好等於可用材料長度。
    allowed_lengths = set(cfg.purchasable_lengths)

    if sum(segments) != cfg.steel_target_length:
        errors.append(
            "steel segment total does not match the resolved Waler steel length"
        )

    # 接頭距支撐限制
    for joint in joints:
        if not is_joint_allowed(joint, cfg):
            errors.append(f"接頭 {joint} 距支撐過近")

    # 每段長度限制
    for seg in segments:
        if seg < cfg.min_piece_length:
            errors.append(f"段長 {seg} 小於最短限制 {cfg.min_piece_length}")
        if seg > cfg.max_piece_length:
            errors.append(f"段長 {seg} 大於最長限制 {cfg.max_piece_length}")
        if seg not in allowed_lengths:
            errors.append(f"段長 {seg} 不在可用材料長度清單中")

    return len(errors) == 0, errors


# =========================
# 4. 配料與評分
# =========================

def segment_ratio_summary(
    segments: List[int],
    cfg: Config,
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """回傳 short/mid/long 的數量與段數比例。"""
    bucket_count = {"short": 0, "mid": 0, "long": 0}
    for seg in segments:
        category = classify_length(seg, cfg)
        if category in bucket_count:
            bucket_count[category] += 1

    total_count = sum(bucket_count.values())
    if total_count == 0:
        return bucket_count, {k: 0.0 for k in bucket_count}

    bucket_ratio = {k: bucket_count[k] / total_count for k in bucket_count}
    return bucket_count, bucket_ratio


def calculate_ratio_penalty(
    segments: List[int],
    cfg: Config,
) -> Tuple[float, Dict[str, float]]:
    """計算分段比例與比例懲罰。"""
    _, bucket_ratio = segment_ratio_summary(segments, cfg)
    target_ratios = {
        "short": cfg.short_segment_ratio_target,
        "mid": cfg.mid_segment_ratio_target,
        "long": cfg.long_segment_ratio_target,
    }
    penalty = sum(
        abs(bucket_ratio[key] - target_ratios[key])
        for key in target_ratios
    ) * cfg.ratio_penalty_weight
    return penalty, bucket_ratio


def allocate_stock_best_fit(
    segments: List[int],
    stock_items: List[Dict],
    purchasable_lengths: List[int],
) -> Optional[Dict]:
    """
    用 best-fit 把每段配到庫存料。
    規則:
    - 每段配一支料
    - 料長必須 >= 段長
    - 優先使用庫存；若庫存不夠則可購買補足

    回傳:
    {
      "assignments": [...],
      "total_waste": ...,           # 仍可計算但不作為評分
      "total_bought": ...,
      "distinct_groups": ..., 
      "length_variation": ..., 
    }
    """
    inventory = expand_stock_items(stock_items)
    used = [False] * len(inventory)

    global allocate_call_count, allocate_total_time
    allocate_start = time.perf_counter()
    assignments = []
    total_waste = 0
    total_bought = 0
    available_lengths = sorted(purchasable_lengths)

    # 先配長段
    for seg in sorted(segments, reverse=True):
        best_idx = next(
            (i for i, stock in enumerate(inventory)
             if not used[i] and stock["stock_length"] == seg),
            None,
        )

        if best_idx is not None:
            used[best_idx] = True
            chosen = inventory[best_idx]
            bought = False
        else:
            if seg not in available_lengths:
                allocate_elapsed = time.perf_counter() - allocate_start
                allocate_call_count += 1
                allocate_total_time += allocate_elapsed
                return None
            total_bought += 1
            chosen = {
                "stock_id": f"BUY-{seg}#{total_bought}",
                "stock_group": f"A{seg}",
                "stock_length": seg,
            }
            bought = True

        assignments.append(
            {
                "segment_length": seg,
                "stock_id": chosen["stock_id"],
                "stock_group": chosen["stock_group"],
                "stock_length": chosen["stock_length"],
                "waste": chosen["stock_length"] - seg,
                "bought": bought,
            }
        )
        total_waste += chosen["stock_length"] - seg

    assignments.sort(key=lambda x: x["segment_length"], reverse=True)

    stock_lengths = [a["stock_length"] for a in assignments]
    distinct_groups = len({a["stock_group"] for a in assignments})
    length_variation = max(stock_lengths) - min(stock_lengths) if stock_lengths else 0

    under_4000_segment_count = sum(1 for seg in segments if seg < 4000)

    allocate_elapsed = time.perf_counter() - allocate_start
    allocate_call_count += 1
    allocate_total_time += allocate_elapsed
    return {
        "assignments": assignments,
        "total_waste": total_waste,
        "total_bought": total_bought,
        "distinct_groups": distinct_groups,
        "length_variation": length_variation,
        "under_4000_segment_count": under_4000_segment_count,
    }


def evaluate_individual(
    individual: List[int],
    cfg: Config,
    stock_items: List[Dict]
) -> Dict:
    global evaluate_count, evaluate_total_time
    evaluate_start = time.perf_counter()
    """
    評估個體，回傳完整結果。
    score 越低越好。
    """
    joints, segments = decode_individual(individual, cfg)
    valid, errors = validate_segments(joints, segments, cfg)

    # 大懲罰：基本幾何規則不符
    if not valid:
        penalty = 1_000_000 + 50_000 * len(errors)
        evaluate_elapsed = time.perf_counter() - evaluate_start
        evaluate_count += 1
        evaluate_total_time += evaluate_elapsed
        return {
            "individual": individual[:],
            "joints": joints,
            "segments": segments,
            "valid": False,
            "errors": errors,
            "assignments": [],
            "total_waste": None,
            "ratio_penalty": None,
            "joint_count": len(joints),
            "score": penalty,
        }

    # 配料
    alloc = allocate_stock_best_fit(segments, stock_items, cfg.purchasable_lengths)
    if alloc is None:
        evaluate_elapsed = time.perf_counter() - evaluate_start
        evaluate_count += 1
        evaluate_total_time += evaluate_elapsed
        return {
            "individual": individual[:],
            "joints": joints,
            "segments": segments,
            "valid": False,
            "errors": ["無法配料，可能無合適庫存或可購買長度"],
            "assignments": [],
            "total_waste": None,
            "buy_count": None,
            "distinct_groups": None,
            "length_variation": None,
            "joint_count": len(joints),
            "score": 800_000 + len(joints) * 1000,
        }

    joint_count = len(joints)
    buy_count = alloc["total_bought"]
    distinct_groups = alloc["distinct_groups"]
    length_variation = alloc["length_variation"]
    under_4000_segment_count = alloc["under_4000_segment_count"]
    ratio_penalty, segment_ratios = calculate_ratio_penalty(segments, cfg)

    # 綜合評分：
    # 1) 優先使用庫存；若使用購買料，分數大幅扣除
    # 2) 儘量符合短/中/長段比例目標
    # 3) 儘量避免段長 <4000
    # 4) 儘量減少不同料種
    # 5) 儘量減少最大/最小料長變化
    # 6) 保留接頭數量作為次要目標
    score = (
        buy_count * 100_000
        + ratio_penalty
        + under_4000_segment_count * 100_000
        + distinct_groups * 5_000
        + length_variation
        + joint_count * 1000
    )

    result = {
        "individual": individual[:],
        "joints": joints,
        "segments": segments,
        "valid": True,
        "errors": [],
        "assignments": alloc["assignments"],
        "total_waste": alloc["total_waste"],
        "buy_count": buy_count,
        "distinct_groups": distinct_groups,
        "length_variation": length_variation,
        "under_4000_segment_count": under_4000_segment_count,
        "segment_ratios": segment_ratios,
        "ratio_penalty": ratio_penalty,
        "joint_count": joint_count,
        "score": score,
    }
    evaluate_elapsed = time.perf_counter() - evaluate_start
    evaluate_count += 1
    evaluate_total_time += evaluate_elapsed
    return result


# =========================
# 5. GA 運算
# =========================

def repair_individual(individual: List[int], cfg: Config, max_iters: int = 80) -> List[int]:
    """
    修補個體：
    1. 先修硬違規（支撐、太短、太長）
    2. 再修「雖然合法但過短」的段（例如 < preferred_min_piece_length）
    3. 最後嘗試簡化接頭數
    """

    hard_min = cfg.min_piece_length
    preferred_min = getattr(cfg, "preferred_min_piece_length", cfg.min_piece_length)
    hard_max = cfg.max_piece_length

    selected = [p for gene, p in zip(individual, cfg.candidate_joint_points) if gene == 1]
    selected = sorted(set(selected))

    def to_individual(selected_joints: List[int]) -> List[int]:
        joint_set = set(selected_joints)
        return [1 if p in joint_set else 0 for p in cfg.candidate_joint_points]

    def get_points(selected_joints: List[int]) -> List[int]:
        return [0] + selected_joints + [cfg.steel_target_length]

    def get_segments(selected_joints: List[int]) -> List[int]:
        pts = get_points(selected_joints)
        return [pts[i + 1] - pts[i] for i in range(len(pts) - 1)]

    def is_valid_selected(selected_joints: List[int]) -> bool:
        test_ind = to_individual(selected_joints)
        joints, segments = decode_individual(test_ind, cfg)
        valid, _ = validate_segments(joints, segments, cfg)
        return valid

    def count_preferred_short(selected_joints: List[int]) -> int:
        return sum(1 for seg in get_segments(selected_joints) if seg < preferred_min)

    def remove_invalid_support_joints(selected_joints: List[int]) -> List[int]:
        return [p for p in selected_joints if is_joint_allowed(p, cfg)]

    def try_remove_joint(selected_joints: List[int], joint_to_remove: int) -> Optional[List[int]]:
        new_selected = [p for p in selected_joints if p != joint_to_remove]
        if is_valid_selected(new_selected):
            return new_selected
        return None

    def fix_hard_short_once(selected_joints: List[int]) -> Tuple[List[int], bool]:
        """
        修真正違規的短段（seg < hard_min）
        """
        points = get_points(selected_joints)

        for i in range(len(points) - 1):
            seg = points[i + 1] - points[i]
            if seg < hard_min:
                candidates = []

                # 刪右邊界接頭
                if 0 < i + 1 < len(points) - 1:
                    right_joint = points[i + 1]
                    merged_len = points[i + 2] - points[i] if i + 2 < len(points) else None
                    if merged_len is not None and hard_min <= merged_len <= hard_max:
                        new_selected = [p for p in selected_joints if p != right_joint]
                        if is_valid_selected(new_selected):
                            candidates.append((abs(merged_len - preferred_min), new_selected))

                # 刪左邊界接頭
                if 0 < i < len(points) - 1:
                    left_joint = points[i]
                    merged_len = points[i + 1] - points[i - 1]
                    if hard_min <= merged_len <= hard_max:
                        new_selected = [p for p in selected_joints if p != left_joint]
                        if is_valid_selected(new_selected):
                            candidates.append((abs(merged_len - preferred_min), new_selected))

                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    return candidates[0][1], True

                return selected_joints, False

        return selected_joints, False

    def fix_hard_long_once(selected_joints: List[int]) -> Tuple[List[int], bool]:
        """
        修真正違規的長段（seg > hard_max）
        """
        points = get_points(selected_joints)

        for i in range(len(points) - 1):
            left = points[i]
            right = points[i + 1]
            seg = right - left

            if seg > hard_max:
                candidates = []

                for p in cfg.candidate_joint_points:
                    if p <= left or p >= right:
                        continue
                    if p in selected_joints:
                        continue
                    if not is_joint_allowed(p, cfg):
                        continue

                    left_seg = p - left
                    right_seg = right - p

                    if hard_min <= left_seg <= hard_max and hard_min <= right_seg <= hard_max:
                        new_selected = sorted(selected_joints + [p])
                        if is_valid_selected(new_selected):
                            # 優先：減少 < preferred_min 的段數
                            short_count = count_preferred_short(new_selected)
                            midpoint_pen = abs(p - (left + right) / 2)
                            candidates.append((short_count, midpoint_pen, new_selected))

                if candidates:
                    candidates.sort(key=lambda x: (x[0], x[1]))
                    return candidates[0][2], True

                return selected_joints, False

        return selected_joints, False

    def improve_preferred_short_once(selected_joints: List[int]) -> Tuple[List[int], bool]:
        """
        修「雖然合法，但小於 preferred_min」的段。
        主要做法：優先嘗試刪掉相鄰接頭來合併。
        """
        points = get_points(selected_joints)
        current_short_count = count_preferred_short(selected_joints)

        best_candidate = None
        best_short_count = current_short_count

        for i in range(len(points) - 1):
            seg = points[i + 1] - points[i]

            if hard_min <= seg < preferred_min:
                # 刪右邊界接頭
                if 0 < i + 1 < len(points) - 1:
                    right_joint = points[i + 1]
                    new_selected = [p for p in selected_joints if p != right_joint]
                    if is_valid_selected(new_selected):
                        new_short_count = count_preferred_short(new_selected)
                        if new_short_count < best_short_count:
                            best_short_count = new_short_count
                            best_candidate = new_selected

                # 刪左邊界接頭
                if 0 < i < len(points) - 1:
                    left_joint = points[i]
                    new_selected = [p for p in selected_joints if p != left_joint]
                    if is_valid_selected(new_selected):
                        new_short_count = count_preferred_short(new_selected)
                        if new_short_count < best_short_count:
                            best_short_count = new_short_count
                            best_candidate = new_selected

        if best_candidate is not None:
            return best_candidate, True

        return selected_joints, False

    def simplify_joints_once(selected_joints: List[int]) -> Tuple[List[int], bool]:
        """
        如果沒有硬違規，也沒有 preferred short，可以試著減少接頭數。
        刪掉一個接頭後若仍合法，且不增加 preferred short，就接受。
        """
        current_short_count = count_preferred_short(selected_joints)

        for joint in selected_joints:
            new_selected = [p for p in selected_joints if p != joint]
            if is_valid_selected(new_selected):
                new_short_count = count_preferred_short(new_selected)
                if new_short_count <= current_short_count:
                    return new_selected, True

        return selected_joints, False

    # -------------------------------------------------
    # 主流程
    # -------------------------------------------------
    selected = remove_invalid_support_joints(selected)

    for _ in range(max_iters):
        changed = False

        # 1. 先修硬違規
        selected, did_fix = fix_hard_short_once(selected)
        if did_fix:
            changed = True
            continue

        selected, did_fix = fix_hard_long_once(selected)
        if did_fix:
            changed = True
            continue

        # 2. 再修 preferred short（例如 < 4000）
        selected, did_fix = improve_preferred_short_once(selected)
        if did_fix:
            changed = True
            continue

        # 3. 如果已合法且沒有 preferred short，就試著減少接頭
        if is_valid_selected(selected) and count_preferred_short(selected) == 0:
            selected, did_fix = simplify_joints_once(selected)
            if did_fix:
                changed = True
                continue

        if not changed:
            break

    if is_valid_selected(selected):
        return to_individual(selected)

    return build_valid_individual(cfg)


def is_joint_path_feasible(cfg: Config) -> bool:
    """Return True if there is any feasible joint path from 0 to total length."""
    valid_points = [
        p
        for p in cfg.candidate_joint_points
        if is_joint_allowed(p, cfg)
    ]
    nodes = [0] + sorted(valid_points) + [cfg.steel_target_length]
    allowed_lengths = set(cfg.purchasable_lengths)

    visited = [False] * len(nodes)
    visited[0] = True
    stack = [0]

    while stack:
        i = stack.pop()
        start = nodes[i]
        for j in range(i + 1, len(nodes)):
            seg = nodes[j] - start
            if seg > cfg.max_piece_length:
                break
            if cfg.min_piece_length <= seg <= cfg.max_piece_length and seg in allowed_lengths:
                if not visited[j]:
                    visited[j] = True
                    stack.append(j)

    return visited[-1]


def find_valid_joint_sequence(cfg: Config, randomize: bool = False) -> Optional[List[int]]:
    debug_print("DEBUG: ENTER FIND_VALID_JOINT_SEQUENCE")
    points = sorted(
        p
        for p in cfg.candidate_joint_points
        if is_joint_allowed(p, cfg)
    )
    target = cfg.steel_target_length
    nodes = [0] + points + [target]
    n = len(nodes)

    # 初始可行路徑只允許用可用材料長度組成。
    allowed_lengths = set(cfg.purchasable_lengths)

    neighbors = []
    for i, pos in enumerate(nodes):
        next_nodes = []
        for j in range(i + 1, n):
            seg = nodes[j] - pos
            if cfg.min_piece_length <= seg <= cfg.max_piece_length and seg in allowed_lengths:
                next_nodes.append(j)
            elif seg > cfg.max_piece_length:
                break
        neighbors.append(next_nodes)

    branch_counts = [len(x) for x in neighbors]
    visit_count = [0]
    memo: Dict[int, Optional[List[int]]] = {}

    debug_print(f"nodes = {len(nodes)}")
    if branch_counts:
        debug_print(f"avg_branch = {sum(branch_counts)/len(branch_counts):.2f}")
        debug_print(f"max_branch = {max(branch_counts)}")
        debug_print(f"min_branch = {min(branch_counts)}")

    def dfs(idx: int) -> Optional[List[int]]:
        if idx in memo:
            return memo[idx]

        visit_count[0] += 1
        if visit_count[0] % 10000 == 0:
            debug_print(f"DFS visit count = {visit_count[0]}")
        if visit_count[0] > 1000000:
            debug_print("DFS visit count exceeded 1000000, aborting search")
            memo[idx] = None
            return None

        if idx == n - 1:
            result = [nodes[idx]]
            memo[idx] = result
            return result

        next_indices = neighbors[idx][:]
        if randomize:
            next_indices = random.sample(neighbors[idx], len(neighbors[idx]))

        result: Optional[List[int]] = None
        for j in next_indices:
            path = dfs(j)
            if path is not None:
                result = [nodes[idx]] + path
                break

        memo[idx] = result
        return result

    debug_print("START DFS")
    path = dfs(0)
    debug_print("END DFS")
    debug_print(f"DFS total visits = {visit_count[0]}")
    debug_print(f"memo size = {len(memo)}")
    if path is None:
        debug_print("DFS FAILED")
        return None
    debug_print(f"DFS SUCCESS, path length = {len(path)}")
    if path[-1] != target:
        return None
    return [p for p in path[1:-1]]


def build_valid_individual(cfg: Config, max_attempts: int = 100) -> List[int]:
    debug_print("build_valid_individual start")
    if not is_joint_path_feasible(cfg):
        debug_print("DEBUG: no feasible joint path for current config, aborting early")
        return [0] * len(cfg.candidate_joint_points)
    func_start = time.perf_counter()
    debug_print("DEBUG: ENTER BUILD_VALID_INDIVIDUAL")
    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        selected = find_valid_joint_sequence(cfg, randomize=True)
        elapsed = time.perf_counter() - start
        if selected is not None:
            debug_print(
                f"DEBUG: build_valid_individual success on attempt {attempt}/{max_attempts} "
                f"(find_valid_joint_sequence {elapsed:.2f}s)"
            )
            result = [1 if p in selected else 0 for p in cfg.candidate_joint_points]
            debug_print(f"build_valid_individual elapsed {time.perf_counter() - func_start:.6f}s")
            return result
        if attempt % 10 == 0:
            debug_print(
                f"DEBUG: build_valid_individual still searching after {attempt} attempts "
                f"(last attempt {elapsed:.2f}s)"
            )

    debug_print("DEBUG: build_valid_individual randomized search exhausted, trying deterministic fallback")
    start = time.perf_counter()
    selected = find_valid_joint_sequence(cfg, randomize=False)
    elapsed = time.perf_counter() - start
    if selected is not None:
        debug_print(f"DEBUG: build_valid_individual fallback success (find_valid_joint_sequence {elapsed:.2f}s)")
        result = [1 if p in selected else 0 for p in cfg.candidate_joint_points]
        debug_print(f"build_valid_individual elapsed {time.perf_counter() - func_start:.6f}s")
        return result

    debug_print("DEBUG: build_valid_individual failed, returning empty individual")
    result = [0] * len(cfg.candidate_joint_points)
    debug_print(f"build_valid_individual elapsed {time.perf_counter() - func_start:.6f}s")
    return result


def create_individual(cfg: Config) -> List[int]:
    """建立一個合法的初始個體。"""
    debug_print("create_individual start")
    func_start = time.perf_counter()
    debug_print("DEBUG: ENTER CREATE_INDIVIDUAL")
    start = time.perf_counter()
    raw = build_valid_individual(cfg)
    built_elapsed = time.perf_counter() - start
    debug_print(f"DEBUG: create_individual built raw individual in {built_elapsed:.2f}s")
    start_repair = time.perf_counter()
    repaired = repair_individual(raw, cfg)
    repair_elapsed = time.perf_counter() - start_repair
    debug_print(f"DEBUG: repair_individual completed in {repair_elapsed:.2f}s")
    total_elapsed = time.perf_counter() - func_start
    debug_print("create_individual end")
    debug_print(f"create_individual elapsed {total_elapsed:.6f}s")
    return repaired


def initial_population(cfg: Config) -> List[List[int]]:
    debug_print("INITIAL POPULATION START")
    pop: List[List[int]] = []
    start = time.perf_counter()
    for i in range(cfg.population_size):
        debug_print(f"DEBUG: CREATE INDIVIDUAL {i+1}/{cfg.population_size}")
        pop.append(create_individual(cfg))
    elapsed = time.perf_counter() - start
    logger(
        f"初始族群建立完成：數量={len(pop)}，"
        f"耗時={elapsed:.6f} 秒"
    )
    return pop


def tournament_selection(
    population: List[List[int]],
    evaluated: List[Dict],
    k: int
) -> List[int]:
    """
    Tournament selection，分數低者勝。
    """
    idxs = random.sample(range(len(population)), k)
    best_idx = min(idxs, key=lambda i: evaluated[i]["score"])
    return population[best_idx][:]


def crossover(parent1: List[int], parent2: List[int], rate: float) -> Tuple[List[int], List[int]]:
    """
    單點交配。
    """
    if random.random() > rate or len(parent1) <= 1:
        return parent1[:], parent2[:]

    cut = random.randint(1, len(parent1) - 1)
    child1 = parent1[:cut] + parent2[cut:]
    child2 = parent2[:cut] + parent1[cut:]

    return child1, child2


def mutate(individual: List[int], rate: float) -> List[int]:
    """
    位元翻轉突變。
    """
    mutated = individual[:]
    for i in range(len(mutated)):
        if random.random() < rate:
            mutated[i] = 1 - mutated[i]
    return mutated


def _reset_performance_counters() -> None:
    global evaluate_count, evaluate_total_time, allocate_call_count, allocate_total_time

    evaluate_count = 0
    evaluate_total_time = 0.0
    allocate_call_count = 0
    allocate_total_time = 0.0


def _run_generations(
    population: List[List[int]],
    cfg: Config,
    stock_items: List[Dict],
    generation_count: int,
    start_generation: int,
    history_out: Optional[List[Dict]] = None,
) -> Tuple[List[List[int]], List[Dict]]:
    evaluated_for_population = [
        evaluate_individual(individual, cfg, stock_items)
        for individual in population
    ]

    for generation_offset in range(generation_count):
        gen_start = time.perf_counter()
        sorted_evaluated = sorted(
            evaluated_for_population,
            key=lambda x: x["score"],
        )

        # Elite 保留
        elite_individuals = [
            item["individual"][:]
            for item in sorted_evaluated[: cfg.elite_size]
        ]

        # 建新族群
        new_population = elite_individuals[:]

        while len(new_population) < cfg.population_size:
            parent1 = tournament_selection(population, evaluated_for_population, cfg.tournament_k)
            parent2 = tournament_selection(population, evaluated_for_population, cfg.tournament_k)

            child1, child2 = crossover(parent1, parent2, cfg.crossover_rate)
            child1 = mutate(child1, cfg.mutation_rate)
            child2 = mutate(child2, cfg.mutation_rate)

            child1 = repair_individual(child1, cfg)
            child2 = repair_individual(child2, cfg)

            new_population.append(child1)
            if len(new_population) < cfg.population_size:
                new_population.append(child2)

        population = new_population
        evaluated_for_population = [
            evaluate_individual(individual, cfg, stock_items)
            for individual in population
        ]
        best = min(evaluated_for_population, key=lambda item: item["score"])
        current_generation = start_generation + generation_offset + 1

        if history_out is not None:
            valid_items = [
                item
                for item in evaluated_for_population
                if item.get("valid")
            ]
            valid_signatures = {
                (
                    tuple(item.get("segments", []) or []),
                    tuple(item.get("joints", []) or []),
                )
                for item in valid_items
            }
            best_valid = min(
                valid_items,
                key=lambda item: item["score"],
                default=None,
            )
            history_out.append({
                "generation": current_generation,
                "best_score": float(best["score"]),
                "best_valid_score": (
                    None
                    if best_valid is None
                    else float(best_valid["score"])
                ),
                "valid_solution_count": len(valid_items),
                "unique_valid_solution_count": len(valid_signatures),
            })

        logger(
            f"第 {current_generation:>3} 代："
            f"最佳分數={best['score']:.2f}，"
            f"有效={'是' if best['valid'] else '否'}，"
            f"最佳方案分段={best['segments']}，"
            f"耗時={time.perf_counter() - gen_start:.6f} 秒"
        )

    return population, evaluated_for_population


def _log_performance_statistics() -> None:
    avg_evaluate = evaluate_total_time / evaluate_count if evaluate_count > 0 else 0.0
    avg_allocate = allocate_total_time / allocate_call_count if allocate_call_count > 0 else 0.0
    logger(
        "評估統計："
        f"次數={evaluate_count}，總耗時={evaluate_total_time:.6f} 秒，"
        f"平均耗時={avg_evaluate:.6f} 秒"
    )
    logger(
        "配料統計："
        f"次數={allocate_call_count}，總耗時={allocate_total_time:.6f} 秒，"
        f"平均耗時={avg_allocate:.6f} 秒"
    )


def _waler_result_signature(item: Dict, cfg: Config) -> Tuple[object, ...]:
    """Canonical uniqueness signature for a formal Waler result."""

    return (
        tuple(item.get("segments", []) or []),
        tuple(item.get("joints", []) or []),
        int(cfg.tail_adjustment),
        int(cfg.tail_gap),
    )


def _top_results(final_evaluated: List[Dict], cfg: Config) -> List[Dict]:
    candidates = final_evaluated

    # 優先只保留有效方案；若沒有任何有效方案，再退回所有方案
    valid_evaluated = [item for item in candidates if item["valid"]]
    if valid_evaluated:
        candidates = valid_evaluated

    # 去重：使用完整正式幾何簽章，不只比較材料長度。
    unique = {}
    for item in candidates:
        key = _waler_result_signature(item, cfg)
        if key not in unique or item["score"] < unique[key]["score"]:
            unique[key] = item

    results = list(unique.values())
    results.sort(key=lambda x: (x["score"], _waler_result_signature(x, cfg)))
    top_results = []
    for item in results[: cfg.top_n]:
        enriched = dict(item)
        pieces = [
            ("steel", length)
            for length in item.get("segments", [])
        ]
        if cfg.tail_adjustment > 0:
            pieces.append(("shim", cfg.tail_adjustment))
        enriched.update(
            required_length=cfg.total_length,
            steel_length=cfg.steel_target_length,
            tail_adjustment=cfg.tail_adjustment,
            gap=cfg.tail_gap,
            pieces=pieces,
        )
        top_results.append(enriched)
    if top_results:
        logger(
            f"最終方案摘要：方案數={len(top_results)}，"
            f"最佳分數={top_results[0]['score']:.2f}，"
            f"最佳方案有效={'是' if top_results[0]['valid'] else '否'}"
        )
    else:
        logger("最終方案摘要：方案數=0")
    return top_results


def evolve(
    cfg: Config,
    stock_items: List[Dict],
    seed: int = DEFAULT_SEARCH_POLICY.waler_search_stages[0].random_seed,
    diagnostics_out: Optional[Dict[str, object]] = None,
) -> List[Dict]:
    """建立初始族群並執行 cfg.generations 代。"""
    _reset_performance_counters()
    debug_print("DEBUG: ENTER EVOLVE")
    random.seed(seed)
    debug_print("DEBUG: START INITIAL_POPULATION")
    population = initial_population(cfg)
    debug_print("DEBUG: END INITIAL_POPULATION")

    generation_history: List[Dict] = []
    population, final_evaluated = _run_generations(
        population,
        cfg,
        stock_items,
        cfg.generations,
        start_generation=0,
        history_out=generation_history,
    )

    _log_performance_statistics()
    results = _top_results(final_evaluated, cfg)
    if diagnostics_out is not None:
        valid_items = [item for item in final_evaluated if item.get("valid")]
        unique_valid_signatures = {
            _waler_result_signature(item, cfg)
            for item in valid_items
        }
        diagnostics_out.clear()
        diagnostics_out.update({
            "candidate_count": len(final_evaluated),
            "valid_candidate_count": len(valid_items),
            "unique_valid_solution_count": len(unique_valid_signatures),
            "generation_history": generation_history,
            "best_score_history": [
                float(record["best_valid_score"])
                if record.get("best_valid_score") is not None
                else float(record["best_score"])
                for record in generation_history
            ],
            "result_count": len(results),
            "seed": int(seed),
            "generations": int(cfg.generations),
            "population_size": int(cfg.population_size),
        })
    return results


# =========================
# 診斷工具
# =========================

def build_neighbors(cfg: Config) -> Tuple[List[int], List[List[int]]]:
    """
    建立節點與鄰接表。
    nodes: [0] + 候選接頭點 + [終點]
    neighbors[i]: 從 nodes[i] 出發，可以合法跳到哪些下一個節點索引
    """
    points = sorted(cfg.candidate_joint_points)
    target = cfg.steel_target_length
    nodes = [0] + points + [target]
    n = len(nodes)

    allowed_lengths = set(cfg.purchasable_lengths)

    neighbors: List[List[int]] = []
    for i, pos in enumerate(nodes):
        next_nodes = []
        for j in range(i + 1, n):
            seg = nodes[j] - pos
            if cfg.min_piece_length <= seg <= cfg.max_piece_length and seg in allowed_lengths:
                next_nodes.append(j)
            elif seg > cfg.max_piece_length:
                break
        neighbors.append(next_nodes)

    return nodes, neighbors


def diagnose_search_space(cfg: Config, stock_items: List[Dict], sample_population_size: int = 120) -> None:
    
    """
    診斷搜尋空間與初始族群狀況。
    """
    print("\n" + "=" * 100)
    print("搜尋空間診斷報告")
    print("=" * 100)

    # -------------------------------------------------
    # 1. 候選點 / 合法點
    # -------------------------------------------------
    total_candidate_points = len(cfg.candidate_joint_points)
    valid_joint_points = [p for p in cfg.candidate_joint_points if is_joint_allowed(p, cfg)]
    valid_candidate_points = len(valid_joint_points)

    print(f"總長度 total_length: {cfg.total_length}")
    print(f"可用材料長度: {sorted(cfg.purchasable_lengths)}")
    print(f"候選接頭點總數: {total_candidate_points}")
    print(f"合法接頭點總數(通過支撐距離限制): {valid_candidate_points}")

    if total_candidate_points > 0:
        valid_ratio = valid_candidate_points / total_candidate_points
        print(f"合法接頭點比例: {valid_ratio:.2%}")
    else:
        print("合法接頭點比例: 無法計算（候選點為 0）")

    # -------------------------------------------------
    # 2. 分支數診斷（不含支撐點限制的鄰接圖）
    # 注意：這裡使用 candidate_joint_points 建圖
    # 真正是否合法還要靠 validate_segments 再判斷
    # -------------------------------------------------
    nodes, neighbors = build_neighbors(cfg)

    branch_counts = [len(x) for x in neighbors[:-1]]  # 最後一個終點通常沒有下一步
    if branch_counts:
        avg_branch = sum(branch_counts) / len(branch_counts)
        max_branch = max(branch_counts)
        min_branch = min(branch_counts)

        print("\n[分支數統計]")
        print(f"節點總數(含起點與終點): {len(nodes)}")
        print(f"平均分支數: {avg_branch:.2f}")
        print(f"最大分支數: {max_branch}")
        print(f"最小分支數: {min_branch}")

        # 你也可以看有多少節點是死路
        dead_end_count = sum(1 for c in branch_counts if c == 0)
        print(f"死路節點數(沒有合法下一步): {dead_end_count}")
    else:
        print("\n[分支數統計]")
        print("沒有可分析的節點。")

    # -------------------------------------------------
    # 3. 初始族群診斷
    # -------------------------------------------------
    print("\n[初始族群診斷]")
    raw_population = [build_valid_individual(cfg) for _ in range(sample_population_size)]
    repaired_population = [repair_individual(ind, cfg) for ind in raw_population]

    raw_eval = [evaluate_individual(ind, cfg, stock_items) for ind in raw_population]
    repaired_eval = [evaluate_individual(ind, cfg, stock_items) for ind in repaired_population]

    raw_valid = sum(1 for x in raw_eval if x["valid"])
    repaired_valid = sum(1 for x in repaired_eval if x["valid"])

    print(f"repair 前有效率: {raw_valid / sample_population_size:.2%}")
    print(f"repair 後有效率: {repaired_valid / sample_population_size:.2%}")

    sample_population = [create_individual(cfg) for _ in range(sample_population_size)]
    evaluated = [evaluate_individual(ind, cfg, stock_items) for ind in sample_population]

    # 有效方案比例
    valid_count = sum(1 for item in evaluated if item["valid"])
    print(f"抽樣初始族群數量: {sample_population_size}")
    print(f"有效方案數量: {valid_count}")
    print(f"有效方案比例: {valid_count / sample_population_size:.2%}")

    # 不同分段方案數量（看多樣性）
    unique_segments = {tuple(item["segments"]) for item in evaluated}
    print(f"不同分段方案數量(去重後): {len(unique_segments)}")
    print(f"分段多樣性比例: {len(unique_segments) / sample_population_size:.2%}")

    # 分數統計
    scores = [item["score"] for item in evaluated]
    if scores:
        best_score = min(scores)
        worst_score = max(scores)
        avg_score = sum(scores) / len(scores)

        print("\n[初始族群分數統計]")
        print(f"最佳分數(best): {best_score:.2f}")
        print(f"平均分數(avg): {avg_score:.2f}")
        print(f"最差分數(worst): {worst_score:.2f}")

    # 接頭數統計
    joint_counts = [item["joint_count"] for item in evaluated]
    if joint_counts:
        avg_joint_count = sum(joint_counts) / len(joint_counts)
        print("\n[初始族群接頭數統計]")
        print(f"最少接頭數: {min(joint_counts)}")
        print(f"平均接頭數: {avg_joint_count:.2f}")
        print(f"最多接頭數: {max(joint_counts)}")

    # 顯示前幾個不同方案
    print("\n[初始族群前 10 個不同分段方案（依分數排序）]")
    unique_best = {}
    for item in evaluated:
        key = tuple(item["segments"])
        if key not in unique_best or item["score"] < unique_best[key]["score"]:
            unique_best[key] = item

    preview = list(unique_best.values())
    preview.sort(key=lambda x: x["score"])

    for i, item in enumerate(preview[:10], start=1):
        valid_segments = all(seg in cfg.purchasable_lengths for seg in item['segments'])
        print(
            f"{i:>2}. valid={item['valid']}, "
            f"score={item['score']:.2f}, "
            f"joint_count={item['joint_count']}, "
            f"segments={item['segments']}, "
            f"all_segments_valid={valid_segments}"
        )

    valid_top10 = all(
        all(seg in cfg.purchasable_lengths for seg in item['segments'])
        for item in preview[:10]
    )
    print(f"前 10 個不同方案的段長是否全部在可用材料長度中: {valid_top10}")
    print("=" * 100 + "\n")

# =========================
# 6. 輸出
# =========================

def print_results(results: List[Dict]) -> None:
    if not results:
        print("找不到結果。")
        return

    for i, r in enumerate(results, start=1):
        print("=" * 90)
        print(f"方案 {i}")
        print(f"是否有效: {r['valid']}")
        print(f"分段長度: {r['segments']}")
        print(f"接頭位置: {r['joints']}")
        print(f"接頭數量: {r['joint_count']}")

        print(f"購買數量: {r.get('buy_count', 0)}")
        print(f"短段 (<4000) 數: {r.get('under_4000_segment_count', 0)}")
        print(f"使用料種數: {r.get('distinct_groups', 0)}")
        print(f"料長變化: {r.get('length_variation', 0)} mm")
        ratios = r.get("segment_ratios", {"short": 0, "mid": 0, "long": 0})
        print(
            f"段長比例: 短段 {ratios['short']:.0%}, 中段 {ratios['mid']:.0%}, 長段 {ratios['long']:.0%}"
        )
        print(f"比例懲罰: {r.get('ratio_penalty', 0):.2f}")
        print(f"綜合分數: {r['score']:.2f}")

        if r["errors"]:
            print("錯誤/警告:")
            for err in r["errors"]:
                print(f"  - {err}")

        if r["assignments"]:
            print("材料配置:")
            for a in r["assignments"]:
                source = "購買" if a.get("bought") else "庫存"
                print(
                    f"  段長 {a['segment_length']:>5} mm "
                    f"<- {source} {a['stock_id']} / {a['stock_group']} "
                    f"({a['stock_length']:>5} mm)"
                )


# =========================
# 7. 主程式
# =========================

if __name__ == "__main__":
    print("程式啟動中，請在跳出的視窗中輸入庫存數量...", flush=True)
    default_total_length = 95500
    default_support_points = [
        2050, 3550, 4550, 7050, 9550, 11550, 13050, 14550,
        17550, 19050, 20550, 23550, 25050, 26550, 29550, 31050,
        32550, 34550, 36050, 37550, 40550, 42050, 43550, 46550,
        48050, 49550, 52050, 53550, 55050, 58050, 59550, 61050,
        64050, 65550, 67050, 70050, 71550, 73050, 76050, 77550,
        79050, 82050, 83550, 85050, 86050, 88550, 91050, 92050,
        93550,
    ]

    config_input = get_initial_config_from_gui(
        default_total_length,
        default_support_points,
    )

    if config_input is None or config_input.get("total_length") is None:
        print("使用者取消輸入，程式結束。")
    else:
        default_qty_map = {
            1000: 4,
            1500: 2,
            2000: 13,
            2500: 5,
            3000: 9,
            3500: 9,
            4000: 19,
            4500: 23,
            5000: 50,
            5500: 46,
            6000: 59,
            6500: 48,
            7000: 67,
            7500: 57,
            8000: 86,
            8500: 55,
            9000: 78,
            9500: 0,
            10000: 66,
        }

        available_lengths = sorted(default_qty_map.keys())

        cfg = Config(
            total_length=config_input["total_length"],
            support_points=config_input["support_points"],
            min_piece_length=1000,
            max_piece_length=10000,
            joint_clearance_to_support=300,
            candidate_joint_step=500,
            purchasable_lengths=available_lengths,
            short_segment_ratio_target=config_input["short_segment_ratio_target"],
            mid_segment_ratio_target=config_input["mid_segment_ratio_target"],
            long_segment_ratio_target=config_input["long_segment_ratio_target"],
            population_size=120,
            generations=200,
            crossover_rate=0.85,
            mutation_rate=0.08,
            elite_size=8,
            tournament_k=4,
            top_n=5,
        )

        stock_items = get_stock_items_from_gui(
            available_lengths,
            default_qty_map=default_qty_map
        )

        if stock_items is None:
            print("使用者取消輸入，程式結束。")
        else:
            diagnose_search_space(cfg, stock_items, sample_population_size=120)
            results = evolve(cfg, stock_items, seed=42)
            print_results(results)
            input("\n按 Enter 鍵結束程式...")
