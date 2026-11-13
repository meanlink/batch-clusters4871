from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset
from src.schemas.dataset import DatasetInput, CorrectionInput
from src.middlewares.auth import current_user, can_write
from src.services import datasets
from src.services.audit import record
from src.utils.serialization import dataset_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d,created=datasets.create(db,data)
    record(db,u.email,'dataset.create',{'id':d.id,'counts':d.quality.get('counts')})
    db.commit()
    return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records,'raw_records':d.raw_records,'quality':d.quality}
@router.post('/{id}/corrections',status_code=201)
def correct(id:int,data:CorrectionInput,db=Depends(get_db),u=Depends(can_write)):
    if data.origin_id != id:
        raise HTTPException(422,'请求体 origin_id 与路径批次不一致')
    d,created=datasets.correct(db,data)
    if created:
        record(db,u.email,'dataset.correct',{'origin':id,'id':d.id,'counts':d.quality.get('counts')})
        db.commit()
    return {**dataset_dict(d),'idempotent':not created}
