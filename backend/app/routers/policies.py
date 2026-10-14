"""Manager/admin Word policy publishing; no AI usage or second-person approval."""
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import Response as RawResponse
from sqlalchemy.orm import Session
from ..deps import require_roles
from ..models import User
from ..db import get_session
from ..audit import write_audit_log
from ..policy_store import MAX_WORD_BYTES, manifest, publish, restore, undo_publish, root, versions_summary
from ..rule_search import get_index
from .. import policy_store
from ..policy_pricing import differences

router = APIRouter(prefix='/api/policies', tags=['制度版本管理'])
_manager = require_roles('admin','department_manager')

@router.get('/versions')
def versions(response: Response, _:User=Depends(_manager)):
    response.headers['Cache-Control']='private, no-store'
    return {'versions':versions_summary(),'current': get_index().catalog['version']}

@router.post('/publish')
def upload_policy(response: Response, file: UploadFile=File(...), version: str=Form(...), effective_date: date=Form(...), allow_major_change: bool=Form(False),
                        user:User=Depends(_manager), session:Session=Depends(get_session)):
    response.headers['Cache-Control']='private, no-store'
    if not file.filename or not file.filename.lower().endswith('.docx'):
        raise HTTPException(422,'请上传docx格式的考核制度')
    content=file.file.read(MAX_WORD_BYTES+1)
    if len(content)>MAX_WORD_BYTES:
        raise HTTPException(413,'Word文件不能超过5MB')
    try:
        with policy_store.policy_transaction(session) as operation:
            entry=publish(content,filename=file.filename,version=version.strip(),effective_date=effective_date.isoformat(),user_id=user.id,allow_major_change=allow_major_change)
            write_audit_log(session,operator_id=user.id,action='policy.publish',target_type='policy',target_id=entry['id'],after={'version':entry['version'],'count':entry['rule_count']})
            write_audit_log(session,operator_id=user.id,action='policy.commit',target_type='policy_operation',target_id=operation,after={'policy':entry['id']})
            session.commit()
            policy_store.finish_transaction()
    except ValueError as e:
        raise HTTPException(422,str(e)) from e
    return {'version':entry['version'],'effective_date':entry['effective_date'],'rule_count':entry['rule_count'],
            'notice':'已经发布。新制度条款可检索；自动金额计算仅适用于经过验证的规则，其余金额按原文人工核定。'}

@router.post('/{policy_id}/restore')
def restore_policy(policy_id:str, user:User=Depends(_manager),session:Session=Depends(get_session)):
    try:
        with policy_store.policy_transaction(session) as operation:
            entry=restore(policy_id)
            write_audit_log(session,operator_id=user.id,action='policy.restore',target_type='policy',target_id=entry['id'],after={'version':entry['version']})
            write_audit_log(session,operator_id=user.id,action='policy.commit',target_type='policy_operation',target_id=operation,after={'policy':entry['id']})
            session.commit()
            policy_store.finish_transaction()
    except ValueError as e: raise HTTPException(404,str(e)) from e
    return {'version':entry['version'],'notice':'已恢复该制度作为当前版本'}

@router.get('/{policy_id}/original')
def original(policy_id:str, _:User=Depends(_manager)):
    entry=next((v for v in manifest()['versions'] if v['id']==policy_id),None)
    if not entry: raise HTTPException(404,'制度版本不存在')
    path=root()/entry['file']
    if not path.is_file(): raise HTTPException(404,'原始Word文件缺失')
    return RawResponse(content=path.read_bytes(),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition':f'attachment; filename="policy-{entry["id"]}.docx"','Cache-Control':'private, no-store'})


@router.post('/preview')
def preview_policy(file: UploadFile=File(...), version: str=Form(...), effective_date: date=Form(...), _:User=Depends(_manager)):
    if not file.filename or not file.filename.lower().endswith('.docx'):
        raise HTTPException(422, '请上传docx格式的考核制度')
    content = file.file.read(MAX_WORD_BYTES + 1)
    if len(content) > MAX_WORD_BYTES:
        raise HTTPException(413, 'Word文件不能超过5MB')
    try:
        catalog = policy_store.parse_word(content, version=version, effective_date=effective_date.isoformat(), filename=file.filename)
        return {'rule_count': len(catalog['rules']), 'warnings': catalog['parse_warnings'], 'diff': differences(catalog, get_index())}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
