from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.reconcile import reconcile
from src.utils.serialization import checksum
import time


def _quality_report(raw_records):
    """核对原始记录，返回（有效记录，质量报告）。无效/冲突不再让整次接入失败。"""
    report = reconcile(raw_records)
    quality = {
        'counts': report['counts'],
        'duplicates': report['duplicates'],
        'isolated': report['isolated'],
        'groups': report['groups'],
    }
    return report['valid_records'], quality


def _assert_name_free(db, name):
    if db.scalar(select(Dataset).where(Dataset.name == name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')


def create(db, data):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    _assert_name_free(db, name)
    valid_records, quality = _quality_report(data.records)
    d = Dataset(
        name=name, source=data.source, records=valid_records,
        raw_records=data.records, quality=quality,
        origin_id=None, correction_key=None,
        checksum=checksum(valid_records), created_at=time.time(),
    )
    db.add(d)
    db.flush()
    return d, True


def correct(db, data):
    """基于原批次生成修正后的新数据批次。

    幂等键 = 原批次 id + 本次修正记录内容指纹；同一次修正重复执行直接返回已生成批次，
    不新增。原批次及其分析任务保持不变。任何校验失败都在提交前抛错，不留半成品。
    """
    origin = db.get(Dataset, data.origin_id)
    if not origin:
        raise HTTPException(404, '原数据批次不存在，无法基于它修正')
    key = checksum(data.records)
    existing = db.scalar(
        select(Dataset).where(Dataset.origin_id == origin.id, Dataset.correction_key == key)
    )
    if existing:
        return existing, False
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    _assert_name_free(db, name)
    valid_records, quality = _quality_report(data.records)
    d = Dataset(
        name=name, source=data.source, records=valid_records,
        raw_records=data.records, quality=quality,
        origin_id=origin.id, correction_key=key,
        checksum=checksum(valid_records), created_at=time.time(),
    )
    db.add(d)
    db.flush()
    return d, True
