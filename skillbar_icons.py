"""Portable catalog of the user's clear FF14 PNG assets."""
import json
import re
from pathlib import Path
from PySide6.QtGui import QPixmap
from skillbar_model import contained_path


class IconCatalog:
    def __init__(self, root):
        self.root = Path(root)
        manifest = self.root / 'catalog.json'
        data = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'jobs': []}
        self.jobs = data['jobs']
        self.extras=data.get('extras',[])
        self.files = {name for job in self.jobs for name in job['skills']} | set(self.extras)
        index=self.root.parent/'ff14-action-types.json'
        data=json.loads(index.read_text(encoding='utf-8')) if index.is_file() else {}
        by_id={identity:kind for kind in ('ability','gcd') for identity in data.get(kind,())}
        self.action_types={}
        for name in self.files:
            match=re.fullmatch(r'(\d{6})_hr1\.png',Path(name).name)
            if match and int(match[1]) in by_id:self.action_types[name]=by_id[int(match[1])]
        self.ability_icons=frozenset(name for name,kind in self.action_types.items() if kind=='ability')
        self._cache = {}

    def pixmap(self, name):
        if not name:
            return QPixmap()
        if name not in self._cache:
            path = contained_path(self.root, name)
            self._cache[name] = QPixmap(str(path)) if path and path.is_file() else QPixmap()
            if name == 'frame.png' and self._cache[name].width() > 96:
                # Exact crop used by the approved preview, excluding adjacent tiles.
                self._cache[name] = self._cache[name].copy(4, 3, 88, 91)
        return self._cache[name]
