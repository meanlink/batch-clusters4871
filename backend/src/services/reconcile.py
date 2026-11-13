"""批次接入核对（reconciliation）。

补传文件会重复带入同一实验釜批次。这里按 batch_id 做整组核对：

- 相同工况（四个工况字段逐值一致）的重复行：只保留第一条，其余计为重复。
- 同一 batch_id 出现互不一致的工况（工况冲突）：整组隔离，不进入分群。
- 任一工况字段缺失、非有限数值、釜压/时间非正、收率越界等无效工况：整组隔离。
- 分群（analyze）只消费核对后的有效批次。

本模块只依赖标准库，保证规则可独立、确定性地测试。
"""
import math

# 与 services.business 的工况特征保持一致；此处本地定义以避免引入 numpy/sklearn 依赖。
FEATURES = ["temperature_c", "pressure_bar", "residence_min", "yield_pct"]
LABELS = ["反应温度(℃)", "釜压(bar)", "停留时间(min)", "收率(%)"]

BATCH_KEY = "batch_id"


def _row_error(row):
    """返回单行的无效原因；有效时返回 None。"""
    bid = row.get(BATCH_KEY)
    if bid is None or (isinstance(bid, str) and not bid.strip()):
        return "缺少批次号 batch_id"
    problems = []
    for key, label in zip(FEATURES, LABELS):
        value = row.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{label}缺失")
            continue
        if isinstance(value, bool):
            problems.append(f"{label}必须为数值")
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            problems.append(f"{label}不是有限数值")
            continue
        if not math.isfinite(number):
            problems.append(f"{label}不是有限数值")
            continue
        if key in ("pressure_bar", "residence_min") and number <= 0:
            problems.append(f"{label}必须为正数")
        if key == "yield_pct" and not 0 <= number <= 100:
            problems.append(f"{label}须在0~100之间")
    if problems:
        return "无效工况：" + "、".join(problems)
    return None


def _condition(row):
    """工况指纹：四个特征的有限浮点值元组。调用前须确认该行无字段错误。"""
    return tuple(float(row[k]) for k in FEATURES)


def reconcile(raw_records):
    """按批次号核对原始记录。

    返回 dict：
      valid_records: 去重后可用于分群的记录（每条一个 batch_id）
      counts:        raw / valid / duplicate / isolated 计数
      duplicates:    被丢弃的重复行明细（含保留行定位）
      isolated:      被隔离行明细（含原因；冲突/无效为整组隔离）
      groups:        每个 batch_id 的核对结论，便于页面展示
    恒等关系：raw = valid + duplicate + isolated。
    """
    grouped = {}
    order = []
    for index, row in enumerate(raw_records):
        bid = row.get(BATCH_KEY)
        key = "(空批次号)" if bid is None or (isinstance(bid, str) and not bid.strip()) else str(bid)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((index, row))

    valid_records = []
    duplicates = []
    isolated = []
    groups = []

    for key in order:
        members = grouped[key]
        row_errors = [(idx, _row_error(row)) for idx, row in members]
        invalid = [(idx, reason) for idx, reason in row_errors if reason]

        if invalid:
            # 无效工况：整组隔离，逐行给出该行自身的原因。
            reason_text = "；".join(f"第{idx + 1}行 {reason}" for idx, reason in invalid)
            for idx, row in members:
                own = next((reason for i, reason in row_errors if i == idx and reason), reason_text)
                isolated.append({
                    "row_index": idx + 1,
                    "batch_id": key,
                    "record": row,
                    "reason": own,
                    "category": "invalid",
                })
            groups.append({"batch_id": key, "status": "isolated", "category": "invalid",
                           "rows": len(members), "reason": reason_text})
            continue

        conditions = {(idx, _condition(row)) for idx, row in members}
        distinct = {cond for _, cond in conditions}
        if len(distinct) > 1:
            # 工况冲突：同一批次号对应互不一致的工况，整组隔离。
            reason_text = f"工况冲突：同一批次号存在{len(distinct)}种不同工况"
            for idx, row in members:
                isolated.append({
                    "row_index": idx + 1,
                    "batch_id": key,
                    "record": row,
                    "reason": reason_text,
                    "category": "conflict",
                })
            groups.append({"batch_id": key, "status": "isolated", "category": "conflict",
                           "rows": len(members), "reason": reason_text})
            continue

        # 工况一致：保留首条，其余为重复（补传带入的同一批次）。
        keep_idx, keep_row = members[0]
        kept = {BATCH_KEY: keep_row.get(BATCH_KEY), **{k: float(keep_row[k]) for k in FEATURES}}
        valid_records.append(kept)
        group_dups = []
        for idx, row in members[1:]:
            item = {
                "row_index": idx + 1,
                "batch_id": key,
                "record": row,
                "reason": f"与第{keep_idx + 1}行工况完全一致的重复批次",
                "kept_row_index": keep_idx + 1,
                "category": "duplicate",
            }
            duplicates.append(item)
            group_dups.append(item)
        groups.append({
            "batch_id": key, "status": "valid", "category": "duplicate" if group_dups else "unique",
            "rows": len(members), "kept_row_index": keep_idx + 1,
            "reason": f"保留第{keep_idx + 1}行，去重{len(group_dups)}行" if group_dups else "唯一有效批次",
        })

    counts = {
        "raw": len(raw_records),
        "valid": len(valid_records),
        "duplicate": len(duplicates),
        "isolated": len(isolated),
    }
    return {
        "valid_records": valid_records,
        "counts": counts,
        "duplicates": duplicates,
        "isolated": isolated,
        "groups": groups,
    }
