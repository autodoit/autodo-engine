"""流程图索引与邻接矩阵构建工具。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    from scipy import sparse as _sp  # type: ignore
except Exception:
    _sp = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore


def build_adjacency_matrix_df(
    table: Any,
    uid_list: List[int],
    entities: List[str],
    row_to_entities_fn,
):
    """构建通用二分邻接矩阵（DataFrame）。"""

    if pd is None:
        raise RuntimeError("需要安装 pandas 才能构建邻接矩阵")

    entity_set = set(entities)
    data: Dict[str, List[int]] = {entity: [] for entity in entities}

    for uid in uid_list:
        row = table.loc[uid]
        hits = set(row_to_entities_fn(int(uid), row)).intersection(entity_set)
        for entity in entities:
            data[entity].append(1 if entity in hits else 0)

    return pd.DataFrame(data)


def build_inverted_index(table: Any, field: str, splitter) -> Dict[str, List[int]]:
    """构建反向索引：entity -> uid 列表。"""

    inverted: Dict[str, List[int]] = {}
    for uid in table.index:
        raw = str(table.at[uid, field]) if field in table.columns else ""
        items = splitter(raw)
        for item in items:
            inverted.setdefault(str(item), []).append(int(uid))
    return inverted


def build_inverted_from_adjacency(uid_list: List[int], adjacency_df: Any) -> Dict[str, List[int]]:
    """从邻接矩阵反推出反向索引。"""

    inverted: Dict[str, List[int]] = {str(column): [] for column in adjacency_df.columns}
    for column in adjacency_df.columns:
        values = adjacency_df[column].tolist()
        for uid, value in zip(uid_list, values):
            if int(value):
                inverted[str(column)].append(int(uid))
    return inverted


def sparse_from_inverted(inv: Dict[str, List[int]], uid_list: List[int]):
    """将反向索引转换为 scipy.sparse.csc_matrix。"""

    if np is None or _sp is None:
        raise RuntimeError("需要安装 numpy/scipy 才能生成稀疏矩阵")

    labels = list(inv.keys())
    uid_to_pos = {int(uid): index for index, uid in enumerate(uid_list)}
    rows: List[int] = []
    cols: List[int] = []
    for column_index, label in enumerate(labels):
        for uid in inv[label]:
            position = uid_to_pos.get(int(uid))
            if position is not None:
                rows.append(position)
                cols.append(column_index)

    data = np.ones(len(rows), dtype=bool)
    coo = _sp.coo_matrix((data, (rows, cols)), shape=(len(uid_list), len(labels)), dtype=bool)
    return coo.tocsc(), labels


def build_bitset_index(table: Any, field: str, splitter) -> Tuple[Dict[str, Any], Optional[Dict[int, int]]]:
    """为每个实体构建位集合索引。"""

    uids = list(table.index)
    uid_to_pos = {int(uid): index for index, uid in enumerate(uids)}
    size = len(uids)

    try:
        from pyroaring import BitMap as LocalRoaringBitmap  # type: ignore

        bits: Dict[str, Any] = {}
        for uid in uids:
            raw = str(table.at[uid, field]) if field in table.columns else ""
            for tag in splitter(raw):
                bitmap = bits.get(str(tag))
                if bitmap is None:
                    bitmap = LocalRoaringBitmap()
                    bits[str(tag)] = bitmap
                bitmap.add(int(uid))
        return bits, None
    except Exception:
        pass

    try:
        from bitarray import bitarray as LocalBitarray  # type: ignore

        labels = set()
        rows: List[Tuple[int, str]] = []
        for uid in uids:
            raw = str(table.at[uid, field]) if field in table.columns else ""
            for tag in splitter(raw):
                labels.add(str(tag))
                rows.append((uid_to_pos[int(uid)], str(tag)))

        bits2: Dict[str, Any] = {}
        for tag in labels:
            bitset = LocalBitarray(size)
            bitset.setall(False)
            bits2[tag] = bitset
        for position, tag in rows:
            bits2[tag][position] = True
        return bits2, uid_to_pos
    except Exception:
        pass

    return build_inverted_index(table, field, splitter), None
