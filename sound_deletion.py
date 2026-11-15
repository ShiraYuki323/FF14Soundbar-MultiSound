"""Reversible, transactional removal of library audio; bindings stay intact."""
import json,os,uuid
from pathlib import Path
from app_paths import _atomic_bytes
from skillbar_model import contained_path,relative_name

class SoundTrash:
    def __init__(self,root):self.root=Path(root).resolve();self.state_path=self.root.parent/'.sound-trash.json'
    def state(self):
        return json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {'deleted':[],'batches':[]}
    def deleted_names(self):return set(self.state()['deleted'])
    def save(self,state):_atomic_bytes(self.state_path,json.dumps(state,ensure_ascii=False).encode('utf-8'))
    def delete(self,names):
        names=list(dict.fromkeys(relative_name(n) for n in names));sources=[]
        if not names:return
        for name in names:
            path=contained_path(self.root,name)
            if not name or any(p.startswith('.') for p in Path(name).parts) or path is None or not path.is_file():raise ValueError('音效不存在或路径无效。')
            sources.append(path)
        if len(set(sources))!=len(sources):raise ValueError('同一文件不能重复删除。')
        batch=uuid.uuid4().hex;directory=self.root/'.trash'/batch
        if not directory.resolve().is_relative_to(self.root):raise ValueError('回收区路径无效。')
        directory.mkdir(parents=True);moved=[];state=self.state()
        _atomic_bytes(directory/'manifest.json',json.dumps(names,ensure_ascii=False).encode('utf-8'))
        try:
            for index,path in enumerate(sources):
                target=directory/f'{index}.bin';os.replace(path,target);moved.append((path,target))
            state['deleted']=sorted(set(state['deleted'])|set(names));state['batches'].append({'id':batch,'names':names});self.save(state)
        except Exception:
            for path,target in reversed(moved):os.replace(target,path)
            raise
    def undo(self):
        state=self.state()
        if not state['batches']:raise ValueError('没有可撤销的删除。')
        batch=state['batches'][-1];directory=self.root/'.trash'/batch['id']
        if not directory.resolve().is_relative_to(self.root):raise ValueError('回收区路径无效。')
        pairs=[]
        for index,name in enumerate(batch['names']):
            target=contained_path(self.root,name);source=directory/f'{index}.bin'
            if target.exists():raise ValueError('已有同名音效，不能覆盖恢复：'+name)
            if not source.is_file():raise ValueError('回收文件缺失。')
            pairs.append((source,target))
        moved=[]
        try:
            for source,target in pairs:target.parent.mkdir(parents=True,exist_ok=True);os.replace(source,target);moved.append((source,target))
            state['batches'].pop();state['deleted']=sorted(set(state['deleted'])-set(batch['names']));self.save(state)
        except Exception:
            for source,target in reversed(moved):os.replace(target,source)
            raise
