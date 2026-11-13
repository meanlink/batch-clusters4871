import json

from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models  # noqa: F401  导入以注册全部表到 metadata

# 既有数据库的增量列：接入核对与修正幂等。新库由 create_all 直接建出完整结构。
_ADDED_COLUMNS = {
    'datasets': [
        ('raw_records', 'JSON NULL'),
        ('quality', 'JSON NULL'),
        ('origin_id', 'INT NULL'),
        ('correction_key', 'VARCHAR(64) NULL'),
    ],
}
# 幂等修正的唯一保障：同一原批次 + 同一修正内容指纹只允许一条。
# 用唯一索引实现，MySQL 与 SQLite 均支持，且与模型上的 UniqueConstraint 等效。
_ADDED_INDEXES = {
    'datasets': [('uq_dataset_correction', 'origin_id, correction_key')],
}


def migrate():
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        for table, indexes in _ADDED_INDEXES.items():
            if table not in existing_tables:
                continue
            names = {uc['name'] for uc in inspector.get_unique_constraints(table)}
            names |= {idx['name'] for idx in inspector.get_indexes(table)}
            for name, columns_ddl in indexes:
                if name not in names:
                    conn.execute(text(
                        f'CREATE UNIQUE INDEX {name} ON {table} ({columns_ddl})'))
        # 历史批次回填：原始快照即其全部记录，并补一份核对报告。
        if 'datasets' in existing_tables:
            from src.services.reconcile import reconcile
            rows = conn.execute(text(
                'SELECT id, records FROM datasets WHERE raw_records IS NULL OR quality IS NULL'
            )).fetchall()
            for dataset_id, records_json in rows:
                raw = json.loads(records_json)
                report = reconcile(raw)
                quality = {
                    'counts': report['counts'], 'duplicates': report['duplicates'],
                    'isolated': report['isolated'], 'groups': report['groups'],
                    'backfilled': True,
                }
                conn.execute(text(
                    'UPDATE datasets SET raw_records = :raw, quality = :quality WHERE id = :id'
                ), {'raw': json.dumps(raw, ensure_ascii=False),
                    'quality': json.dumps(quality, ensure_ascii=False), 'id': dataset_id})


if __name__ == '__main__':
    migrate()
